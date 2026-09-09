import Foundation
import CoreLocation

/// The charger dataset, read natively for CarPlay.
///
/// Reads the SAME data.js the web view uses -- the refreshed overlay copy when there is
/// one, the bundled copy otherwise -- so the car never shows older chargers than the phone.
/// The file is `window.PITSTOP_DATA = JSON.parse('…');` with the JSON inside a JS
/// single-quoted string; build_data.py escapes exactly two things (`\` and `'`), so that is
/// exactly what is unescaped here. Anything else after a backslash is left for JSON.
struct Charger {
    let id: Int
    let name: String
    let lat: Double, lon: Double
    let net: String
    let kw: Int, stalls: Int
    let city: String, st: String
    /// brand -> walking distance in metres, food chains only
    let food: [(brand: String, emoji: String, metres: Double)]

    var coordinate: CLLocationCoordinate2D { .init(latitude: lat, longitude: lon) }
}

final class ChargerStore {

    static let shared = ChargerStore()
    private(set) var chargers: [Charger] = []
    private(set) var loaded = false

    func loadIfNeeded() {
        guard !loaded else { return }
        loaded = true
        let overlay = DataUpdater.overlayDir.appendingPathComponent("data.js")
        let bundled = Bundle.main.url(forResource: "Web", withExtension: nil)?.appendingPathComponent("data.js")
        let file = FileManager.default.fileExists(atPath: overlay.path) ? overlay : bundled
        guard let file, let raw = try? String(contentsOf: file, encoding: .utf8) else { return }
        guard let open = raw.range(of: "JSON.parse('"), let close = raw.range(of: "');", options: .backwards) else { return }
        let body = String(raw[open.upperBound..<close.lowerBound])

        var json = ""; json.reserveCapacity(body.utf8.count)
        var it = body.makeIterator()
        while let c = it.next() {
            if c == "\\" {
                guard let n = it.next() else { break }
                if n == "'" || n == "\\" { json.append(n) } else { json.append("\\"); json.append(n) }
            } else { json.append(c) }
        }
        guard let data = json.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sites = root["sites"] as? [[String: Any]],
              let brands = root["brands"] as? [String: [String: Any]],
              let matches = root["matches"] as? [String: [String: [Any]]] else { return }

        var out: [Charger] = []; out.reserveCapacity(sites.count)
        for s in sites {
            guard let id = s["id"] as? Int, let lat = s["lat"] as? Double, let lon = s["lon"] as? Double else { continue }
            var food: [(String, String, Double)] = []
            if let m = matches[String(id)] {
                for (brand, v) in m {
                    guard let b = brands[brand], (b["cat"] as? String) == "food",
                          v.count >= 2, let dx = v[0] as? Double, let dy = v[1] as? Double else { continue }
                    // matches hold metre offsets from the charger; distance is the hypotenuse
                    food.append((brand, b["e"] as? String ?? "", (dx * dx + dy * dy).squareRoot()))
                }
                food.sort { $0.2 < $1.2 }
            }
            out.append(Charger(id: id, name: s["name"] as? String ?? "Charger", lat: lat, lon: lon,
                               net: s["net"] as? String ?? "", kw: s["kw"] as? Int ?? 0, stalls: s["stalls"] as? Int ?? 0,
                               city: s["city"] as? String ?? "", st: s["st"] as? String ?? "",
                               food: food.map { (brand: $0.0, emoji: $0.1, metres: $0.2) }))
        }
        chargers = out
    }

    /// Chargers with somewhere to eat within a walk, nearest first. This is the whole
    /// product on the car screen: not "chargers near me", "chargers near me where you can
    /// eat while you wait".
    func nearestWithFood(to loc: CLLocation, limit: Int = 12, withinMiles: Double = 40) -> [(Charger, CLLocationDistance)] {
        loadIfNeeded()
        let maxM = withinMiles * 1609.34
        var hits: [(Charger, CLLocationDistance)] = []
        for c in chargers where !c.food.isEmpty {
            let d = loc.distance(from: CLLocation(latitude: c.lat, longitude: c.lon))
            if d <= maxM { hits.append((c, d)) }
        }
        hits.sort { $0.1 < $1.1 }
        return Array(hits.prefix(limit))
    }
}
