import WidgetKit
import SwiftUI
import CoreLocation

/// "Nearest stop with food" on the home screen. One glance answers the question the whole
/// product exists for, without opening anything; a tap opens the app on that stop.
///
/// Location comes from the app's last fix (saved into the App Group by the location bridge)
/// rather than from the widget asking CoreLocation itself: widget location is throttled and
/// often stale anyway, and this way the widget never shows a permission prompt of its own.
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
        store.dataURL = { ChargerStore.groupDir?.appendingPathComponent("data.js") }
        var entry = StopEntry(date: Date(), charger: nil, miles: 0, stale: false)
        if let fix = UserDefaults(suiteName: ChargerStore.groupID)?.array(forKey: "lastFix") as? [Double], fix.count == 3 {
            let loc = CLLocation(latitude: fix[0], longitude: fix[1])
            let age = Date().timeIntervalSince1970 - fix[2]
            if let (c, d) = store.nearestWithFood(to: loc, limit: 1).first {
                entry = StopEntry(date: Date(), charger: c, miles: d / 1609.34, stale: age > 86_400)
            }
        }
        // Re-run every 30 minutes; the app refreshes the fix whenever it is used.
        completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(1800))))
    }

    private var sample: StopEntry {
        StopEntry(date: Date(),
                  charger: Charger(id: 0, name: "Barstow - Tesla Supercharger", lat: 0, lon: 0, net: "Tesla Supercharger",
                                   kw: 250, stalls: 40, city: "Barstow", st: "CA",
                                   food: [(brand: "IHOP", emoji: "🥞", metres: 240), (brand: "In-N-Out", emoji: "🍔", metres: 400)]),
                  miles: 1.2, stale: false)
    }
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
                        Text(entry.stale ? "Near your last spot" : "Nearest stop with food")
                            .font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                    }
                    Text(c.name).font(.system(size: family == .systemSmall ? 14 : 16, weight: .bold))
                        .lineLimit(2).minimumScaleFactor(0.85)
                    Text(String(format: "%.1f mi · %d kW · %d stalls", entry.miles, c.kw, c.stalls))
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    HStack(spacing: 6) {
                        ForEach(Array(c.food.prefix(family == .systemSmall ? 2 : 3).enumerated()), id: \.offset) { _, f in
                            Text("\(f.emoji) \(f.brand) \(max(1, Int((f.metres / 80).rounded()))) min")
                                .font(.caption2.weight(.semibold)).lineLimit(1)
                                .padding(.horizontal, 7).padding(.vertical, 4)
                                .background(Color.primary.opacity(0.08), in: Capsule())
                        }
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
