import AppIntents
import CoreLocation
import SwiftUI

/// Siri and Shortcuts support.
///
/// This is the clearest native capability the product has that a website cannot reach: you
/// ask out loud, hands on the wheel, and get an answer without unlocking anything. It also
/// needs no entitlement and no approval from Apple, unlike CarPlay.
///
/// The answer is spoken AND shown, and every result is a real charger from the same bundled
/// data the app and widget read, so the three surfaces can never disagree.

/// One-shot location for an intent. Intents run briefly and outside the app's UI, so a fix
/// that has not arrived in six seconds is not coming; the intent says so rather than hanging.
private final class IntentLocation: NSObject, CLLocationManagerDelegate {
    static let shared = IntentLocation()
    private let manager = CLLocationManager()
    private var done: ((CLLocation?) -> Void)?
    private var timer: DispatchWorkItem?

    func fix() async -> CLLocation? {
        await withCheckedContinuation { cont in
            DispatchQueue.main.async {
                self.manager.delegate = self
                self.manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
                guard [.authorizedAlways, .authorizedWhenInUse].contains(self.manager.authorizationStatus) else {
                    cont.resume(returning: nil); return
                }
                self.done = { cont.resume(returning: $0) }
                let t = DispatchWorkItem { [weak self] in self?.finish(nil) }
                self.timer = t
                DispatchQueue.main.asyncAfter(deadline: .now() + 6, execute: t)
                self.manager.requestLocation()
            }
        }
    }
    private func finish(_ loc: CLLocation?) {
        timer?.cancel(); timer = nil
        let d = done; done = nil
        d?(loc)
    }
    func locationManager(_ m: CLLocationManager, didUpdateLocations l: [CLLocation]) { finish(l.last) }
    func locationManager(_ m: CLLocationManager, didFailWithError e: Error) { finish(nil) }
}

private func walkMin(_ metres: Double) -> Int { max(1, Int((metres / 80).rounded())) }   // web's 80 m/min

/// The intent's actual answer, independent of Siri.
///
/// Kept separate because Shortcuts cannot reliably run an app intent in the Simulator, so
/// this is the part that can be exercised with real data and real coordinates -- and the
/// part worth being sure about. `NearestStopIntent.perform()` is a thin shell over it.
enum StopAnswer {
    struct Result { let spoken: String; let charger: Charger?; let miles: String }

    static func build(near here: CLLocation?, chain: String?, store: ChargerStore) -> Result {
        // Match case-insensitively but echo back what they actually said: "near a zzzz"
        // reads like a bug when they asked for "Zzzz".
        let typed = chain?.trimmingCharacters(in: .whitespaces)
        let spokenName = (typed?.isEmpty == false) ? typed : nil
        let want = spokenName?.lowercased()

        guard let here else {
            return Result(spoken: "I need location access to find chargers near you. You can turn it on in Settings.",
                          charger: nil, miles: "")
        }
        var hits = store.nearestWithFood(to: here, limit: 12)
        if let w = want { hits = hits.filter { $0.0.food.contains { $0.brand.lowercased().contains(w) } } }
        guard let (c, dist) = hits.first else {
            let what = spokenName.map { "near a \($0)" } ?? "with food"
            return Result(spoken: "I couldn\u{2019}t find a fast charger \(what) within 40 miles.", charger: nil, miles: "")
        }
        let miles = String(format: "%.1f", dist / 1609.34)
        let place = want.flatMap { w in c.food.first { $0.brand.lowercased().contains(w) } } ?? c.food.first
        let eat = place.map { "\($0.brand), about \(walkMin($0.metres)) minutes\u{2019} walk" } ?? "somewhere to eat"
        return Result(spoken: "\(c.name) in \(c.city), \(miles) miles away. \(c.kw) kilowatts, \(c.stalls) stalls, with \(eat).",
                      charger: c, miles: miles)
    }

    /// Points the shared store at whichever data.js is current (refreshed copy, else bundled).
    static func preparedStore() -> ChargerStore {
        let store = ChargerStore.shared
        store.dataURL = {
            let overlay = DataUpdater.overlayDir.appendingPathComponent("data.js")
            if FileManager.default.fileExists(atPath: overlay.path) { return overlay }
            return Bundle.main.url(forResource: "Web", withExtension: nil)?.appendingPathComponent("data.js")
        }
        return store
    }
}

/// "Find a charger with food" — the whole product in one sentence.
struct NearestStopIntent: AppIntent {
    static var title: LocalizedStringResource = "Find a charger with food"
    static var description = IntentDescription(
        "Finds the nearest DC fast charger that has somewhere to eat within a short walk.")
    /// The result is spoken and shown; opening the app would defeat the point of asking.
    static var openAppWhenRun: Bool = false

    @Parameter(title: "Chain", description: "Optional: a chain to look for, like IHOP or Starbucks.")
    var chain: String?

    static var parameterSummary: some ParameterSummary {
        Summary("Find a charger with food near me") { \.$chain }
    }

    func perform() async throws -> some IntentResult & ProvidesDialog & ShowsSnippetView {
        let store = StopAnswer.preparedStore()
        let here = await IntentLocation.shared.fix()
        let r = StopAnswer.build(near: here, chain: chain, store: store)
        return .result(dialog: IntentDialog(stringLiteral: r.spoken),
                       view: StopSnippet(charger: r.charger, miles: r.miles,
                                         message: r.charger == nil ? r.spoken : nil))
    }
}

struct StopSnippet: View {
    let charger: Charger?
    let miles: String
    let message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let c = charger {
                Text(c.name).font(.headline).lineLimit(2)
                Text("\(miles) mi · \(c.kw) kW · \(c.stalls) stalls · \(c.net)")
                    .font(.subheadline).foregroundStyle(.secondary)
                ForEach(Array(c.food.prefix(3).enumerated()), id: \.offset) { _, f in
                    Text("\(f.emoji) \(f.brand) — \(walkMin(f.metres)) min walk").font(.callout)
                }
            } else {
                Text(message ?? "Nothing found").font(.headline)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
    }
}

/// Phrases Siri accepts without the user setting anything up. Each must contain
/// .applicationName, which resolves to the app's name and its short synonyms below.
struct ChargeAndChewShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: NearestStopIntent(),
            phrases: [
                "Find a charger with food in \(.applicationName)",
                "Find me a charging stop in \(.applicationName)",
                "Where can I charge and eat with \(.applicationName)",
                "\(.applicationName) nearest charger"
            ],
            shortTitle: "Charger with food",
            systemImageName: "bolt.car")
    }
}
