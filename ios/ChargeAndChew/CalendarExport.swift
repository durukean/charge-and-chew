import UIKit
import EventKit
import CoreLocation
import EventKitUI

/// One stop of a planned drive, as the page sends it for "Add to calendar".
///
/// The page builds the same events for the web's .ics file; here they arrive as fields, so
/// nothing has to parse iCalendar. The bridge only listens to the app's own page, but a
/// payload is still input: anything out of shape is refused rather than half-added.
struct CalendarStop {
    let uid: String
    let title: String
    let start: Date
    let end: Date
    let timeZone: TimeZone?
    let place: String
    let location: String
    let notes: String
    let latitude: Double
    let longitude: Double
    let url: URL?
    let label: String

    init?(_ d: [String: Any]) {
        guard let uid = d["uid"] as? String, !uid.isEmpty, uid.count <= 200,
              let title = d["title"] as? String, !title.isEmpty, title.count <= 200,
              let s = (d["start"] as? NSNumber)?.doubleValue, let e = (d["end"] as? NSNumber)?.doubleValue,
              s.isFinite, e.isFinite, e > s, e - s <= 6 * 3600_000,
              let lat = (d["lat"] as? NSNumber)?.doubleValue, let lon = (d["lon"] as? NSNumber)?.doubleValue,
              (-90...90).contains(lat), (-180...180).contains(lon) else { return nil }
        let start = Date(timeIntervalSince1970: s / 1000)
        // A plan is for today or the days ahead: nothing from last week, nothing years out.
        guard start > Date().addingTimeInterval(-2 * 86400), start < Date().addingTimeInterval(400 * 86400) else { return nil }
        self.uid = uid; self.title = title; self.start = start
        self.end = Date(timeIntervalSince1970: e / 1000)
        self.timeZone = (d["tz"] as? String).flatMap(TimeZone.init(identifier:))
        self.place = String((d["place"] as? String ?? "").prefix(200))
        self.location = String((d["location"] as? String ?? "").prefix(300))
        self.notes = String((d["notes"] as? String ?? "").prefix(4000))
        self.latitude = lat; self.longitude = lon
        // Only a link back into this app's own site.
        if let raw = d["url"] as? String, let u = URL(string: raw), u.scheme == "https",
           u.host == "chargeandchew.com" { self.url = u } else { self.url = nil }
        self.label = String((d["label"] as? String ?? title).prefix(80))
    }
}

/// "Add to calendar" for a planned drive (batch 9).
///
/// One stop: the system's own event editor, pre-filled, where the user picks the calendar and
/// taps Add. From iOS 17 that editor runs outside the app and needs no permission at all.
/// The whole drive: write-only access (iOS 17+: "add events", never read them), every stop
/// added in one commit, then a confirmation with a way into Calendar. Refused access offers
/// Settings, or the plan as a .ics file through the share sheet.
final class CalendarExport: NSObject {
    private let store = EKEventStore()
    private weak var host: UIViewController?
    /// The UIDs added before, with when: write-only access cannot read the calendar back, so a
    /// second tap on the same drive would silently double every stop.
    private static let addedKey = "cc.calendarAdded"
    /// The stop open in the system editor, recorded as added if the user saves it.
    private var editing: String?

    init(host: UIViewController) { self.host = host }

    func add(_ stops: [CalendarStop], single: Bool, ics: String?, name: String) {
        guard !stops.isEmpty else { return }
        Diag.log("calendar: \(single ? "stop" : "trip"), \(stops.count) event(s)")
        if single { editOne(stops[0], ics: ics, name: name) } else { confirmTrip(stops, ics: ics, name: name) }
    }

    // MARK: one stop

    private func editOne(_ stop: CalendarStop, ics: String?, name: String) {
        if #available(iOS 17.0, *) { presentEditor(stop); return }
        store.requestAccess(to: .event) { [weak self] granted, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                granted ? self.presentEditor(stop) : self.offerFallback(ics: ics, name: name)
            }
        }
    }

    private func presentEditor(_ stop: CalendarStop) {
        guard let host, host.presentedViewController == nil else { return }
        let vc = EKEventEditViewController()
        vc.eventStore = store
        vc.event = event(stop, calendar: nil)
        vc.editViewDelegate = self
        editing = stop.uid
        host.present(vc, animated: true)
    }

    // MARK: the whole drive

    private func confirmTrip(_ stops: [CalendarStop], ics: String?, name: String) {
        let added = UserDefaults.standard.dictionary(forKey: Self.addedKey) as? [String: Double] ?? [:]
        guard stops.contains(where: { added[$0.uid] != nil }), let host, host.presentedViewController == nil else {
            requestAndAdd(stops, ics: ics, name: name); return
        }
        let alert = UIAlertController(
            title: "Already in your calendar",
            message: "You added stops from this drive before. Adding them again puts a second copy in your calendar.",
            preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Add Again", style: .default) { [weak self] _ in
            self?.requestAndAdd(stops, ics: ics, name: name)
        })
        host.present(alert, animated: true)
    }

    private func requestAndAdd(_ stops: [CalendarStop], ics: String?, name: String) {
        let done: (Bool, Error?) -> Void = { [weak self] granted, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                granted ? self.save(stops, ics: ics, name: name) : self.offerFallback(ics: ics, name: name)
            }
        }
        if #available(iOS 17.0, *) { store.requestWriteOnlyAccessToEvents(completion: done) }
        else { store.requestAccess(to: .event, completion: done) }
    }

    private func save(_ stops: [CalendarStop], ics: String?, name: String) {
        guard let cal = store.defaultCalendarForNewEvents else { offerFallback(ics: ics, name: name); return }
        do {
            for s in stops { try store.save(event(s, calendar: cal), span: .thisEvent, commit: false) }
            try store.commit()
        } catch {
            store.reset()
            Diag.log("calendar: save failed: \(error.localizedDescription)")
            offerFallback(ics: ics, name: name)
            return
        }
        Self.remember(stops.map(\.uid))
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        guard let host, host.presentedViewController == nil else { return }
        let alert = UIAlertController(
            title: stops.count == 1 ? "Added to your calendar" : "Added \(stops.count) stops to your calendar",
            message: stops.map(\.label).joined(separator: "\n"),
            preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Open Calendar", style: .default) { _ in
            // calshow: opens Calendar on that moment (seconds since 2001).
            if let u = URL(string: "calshow:\(Int(stops[0].start.timeIntervalSinceReferenceDate))") { UIApplication.shared.open(u) }
        })
        alert.addAction(UIAlertAction(title: "Done", style: .cancel))
        host.present(alert, animated: true)
    }

    private static func remember(_ uids: [String]) {
        var added = UserDefaults.standard.dictionary(forKey: addedKey) as? [String: Double] ?? [:]
        for u in uids { added[u] = Date().timeIntervalSince1970 }
        if added.count > 300 {                       // keep the newest
            for k in added.sorted(by: { $0.value < $1.value }).prefix(added.count - 300).map(\.key) { added[k] = nil }
        }
        UserDefaults.standard.set(added, forKey: addedKey)
    }

    // MARK: building an event

    private func event(_ s: CalendarStop, calendar: EKCalendar?) -> EKEvent {
        let e = EKEvent(eventStore: store)
        e.title = s.title
        e.startDate = s.start
        e.endDate = s.end
        // The stop's own zone: with Calendar's time zone override on, 12:30 pm in Utah stays 12:30 pm.
        e.timeZone = s.timeZone
        e.location = s.location
        let loc = EKStructuredLocation(title: s.place.isEmpty ? s.location : s.place)
        loc.geoLocation = CLLocation(latitude: s.latitude, longitude: s.longitude)
        loc.radius = 100
        e.structuredLocation = loc
        e.notes = s.notes
        e.url = s.url
        if let calendar { e.calendar = calendar }
        return e
    }

    // MARK: no access

    /// Access refused (now or before): Settings, or the plan as a calendar file to send on.
    private func offerFallback(ics: String?, name: String) {
        guard let host, host.presentedViewController == nil else { return }
        let alert = UIAlertController(
            title: "Calendar access is off",
            message: "To add the stops, allow Charge & Chew to add events in Settings. Or share the plan as a calendar file.",
            preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Not Now", style: .cancel))
        alert.addAction(UIAlertAction(title: "Open Settings", style: .default) { _ in
            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
        })
        if let ics, let file = Self.write(ics, name: name) {
            alert.addAction(UIAlertAction(title: "Share File", style: .default) { [weak host] _ in
                let sheet = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                sheet.popoverPresentationController?.sourceView = host?.view
                host?.present(sheet, animated: true)
            })
        }
        host.present(alert, animated: true)
    }

    /// The page's .ics in a temporary file with a safe name.
    static func write(_ ics: String, name: String) -> URL? {
        guard ics.hasPrefix("BEGIN:VCALENDAR"), ics.utf8.count <= 256 * 1024 else { return nil }
        let stem = name.lowercased().hasSuffix(".ics") ? String(name.dropLast(4)) : name
        let base = String(stem.lowercased().unicodeScalars.filter { ("a"..."z").contains($0) || ("0"..."9").contains($0) || $0 == "-" }
            .map(Character.init))
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent((base.isEmpty ? "charge-and-chew" : String(base.prefix(80))) + ".ics")
        do { try ics.write(to: url, atomically: true, encoding: .utf8) } catch { return nil }
        return url
    }
}

extension CalendarExport: EKEventEditViewDelegate {
    func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
        Diag.log("calendar: editor \(action == .saved ? "saved" : action == .canceled ? "canceled" : "deleted")")
        if action == .saved, let uid = editing {
            Self.remember([uid])
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
        editing = nil
        controller.dismiss(animated: true)
    }
}
