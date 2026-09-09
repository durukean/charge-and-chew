import WidgetKit
import SwiftUI
import CoreLocation

/// "Nearest stop with food" on the home screen. One glance answers the question the whole
/// product exists for, without opening anything; a tap opens the app on that stop.
///
/// The widget asks CoreLocation itself, under the containing app's authorization
/// (NSWidgetWantsLocation). iOS asks once, system-wide, whether the app's widgets may use
/// location; after that there are no prompts. Without a fix it shows a one-line nudge.
struct StopEntry: TimelineEntry {
    let date: Date
    let charger: Charger?
    let miles: Double
    let stale: Bool          // the app's fix is over a day old
}

struct Provider: TimelineProvider {
    func placeholder(in: Context) -> StopEntry { sample }
    func getSnapshot(in: Context, completion: @escaping (StopEntry) -> Void) { completion(sample) }

    func getTimeline(in: Context, completion: @escaping (Timeline<StopEntry>) -> Void) {
        let store = ChargerStore.shared
        store.dataURL = { ChargerStore.containingAppWebDir?.appendingPathComponent("data.js") }
        WidgetLocation.shared.fix { loc in
            var entry = StopEntry(date: Date(), charger: nil, miles: 0, stale: false)
            if let loc, let (c, d) = store.nearestWithFood(to: loc, limit: 1).first {
                entry = StopEntry(date: Date(), charger: c, miles: d / 1609.34, stale: false)
            }
            // Re-run every 30 minutes.
            completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(1800))))
        }
    }

    private var sample: StopEntry {
        StopEntry(date: Date(),
                  charger: Charger(id: 0, name: "Barstow - Tesla Supercharger", lat: 0, lon: 0, net: "Tesla Supercharger",
                                   kw: 250, stalls: 40, city: "Barstow", st: "CA",
                                   food: [(brand: "IHOP", emoji: "🥞", metres: 240), (brand: "In-N-Out", emoji: "🍔", metres: 400)]),
                  miles: 1.2, stale: false)
    }
}

/// One-shot location with a short timeout. Widgets run briefly and off the main actor;
/// a fix that has not arrived in four seconds is not coming this cycle.
final class WidgetLocation: NSObject, CLLocationManagerDelegate {
    static let shared = WidgetLocation()
    private let manager = CLLocationManager()
    private var pending: ((CLLocation?) -> Void)?
    private var timer: DispatchWorkItem?

    func fix(_ done: @escaping (CLLocation?) -> Void) {
        DispatchQueue.main.async {
            self.manager.delegate = self
            self.manager.desiredAccuracy = kCLLocationAccuracyKilometer
            guard [.authorizedAlways, .authorizedWhenInUse].contains(self.manager.authorizationStatus) else { return done(nil) }
            self.pending = done
            let t = DispatchWorkItem { [weak self] in self?.finish(nil) }
            self.timer = t
            DispatchQueue.main.asyncAfter(deadline: .now() + 4, execute: t)
            self.manager.requestLocation()
        }
    }
    private func finish(_ loc: CLLocation?) {
        timer?.cancel(); timer = nil
        let p = pending; pending = nil
        p?(loc)
    }
    func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) { finish(locs.last) }
    func locationManager(_ m: CLLocationManager, didFailWithError error: Error) { finish(nil) }
}

struct StopView: View {
    @Environment(\.widgetFamily) var family
    let entry: StopEntry
    private let green = Color(red: 0.29, green: 0.87, blue: 0.5)

    var body: some View {
        Group {
            if let c = entry.charger {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        Image(systemName: "bolt.fill").foregroundStyle(green)
                        Text(family == .systemSmall ? "Nearest with food" : "Nearest stop with food")
                            .font(.caption2.weight(.bold)).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Text(c.name).font(.system(size: family == .systemSmall ? 14 : 16, weight: .bold))
                        .lineLimit(2).minimumScaleFactor(0.85)
                    Text(String(format: "%.1f mi · %d kW · %d stalls", entry.miles, c.kw, c.stalls))
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    // Small widgets stack the chips: two side by side truncated "IHOP" to "IH…".
                    let chips = Array(c.food.prefix(family == .systemSmall ? 2 : 3).enumerated())
                    let chip: (Charger.Place) -> AnyView = { f in AnyView(
                        Text("\(f.emoji) \(f.brand) \(max(1, Int((f.metres / 80).rounded()))) min")
                            .font(.caption2.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
                            .padding(.horizontal, 7).padding(.vertical, 4)
                            .background(Color.primary.opacity(0.08), in: Capsule())) }
                    if family == .systemSmall {
                        VStack(alignment: .leading, spacing: 4) { ForEach(chips, id: \.offset) { _, f in chip(f) } }
                    } else {
                        HStack(spacing: 6) { ForEach(chips, id: \.offset) { _, f in chip(f) } }
                    }
                    Spacer(minLength: 0)
                }
                .widgetURL(URL(string: "ccapp://stop?at=\(c.lat),\(c.lon)&r=10"))
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        Image(systemName: "bolt.fill").foregroundStyle(green)
                        Text("Charge & Chew").font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                    }
                    Text("Open the app and tap locate once — this will show the nearest fast charger with food.")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
                .widgetURL(URL(string: "ccapp://open"))
            }
        }
        .containerBackground(for: .widget) { Color(.systemBackground) }
    }
}

@main
struct ChargeAndChewWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "cc.nearest", provider: Provider()) { StopView(entry: $0) }
            .configurationDisplayName("Nearest stop with food")
            .description("The closest fast charger with somewhere to eat a short walk away.")
            .supportedFamilies([.systemSmall, .systemMedium])
    }
}
