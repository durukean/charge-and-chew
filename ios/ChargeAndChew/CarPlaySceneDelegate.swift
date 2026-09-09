import CarPlay
import CoreLocation
import MapKit

/// The car screen. One template: a point-of-interest map of the nearest fast chargers
/// that have somewhere to eat within a walk, with Directions handed to Apple Maps.
///
/// CarPlay cannot show the web app -- it only renders Apple's templates -- so this is the
/// one part of the product built twice, natively. It is also the genuine native capability
/// that makes the app more than a website in a box. Requires the
/// com.apple.developer.carplay-charging entitlement, which Apple grants per app on request;
/// until then it runs only in the Simulator's CarPlay display.
final class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate, CLLocationManagerDelegate {

    private var interface: CPInterfaceController?
    private let manager = CLLocationManager()
    private let poi = CPPointOfInterestTemplate(title: "Charge & Chew", pointsOfInterest: [], selectedIndex: NSNotFound)

    func templateApplicationScene(_ scene: CPTemplateApplicationScene, didConnect controller: CPInterfaceController) {
        Diag.log("carplay: connected")
        interface = controller
        poi.pointOfInterestDelegate = self
        controller.setRootTemplate(poi, animated: false, completion: nil)
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .denied, .restricted: showEmpty("Turn on Location for Charge & Chew to see chargers near you.")
        default: manager.requestLocation()
        }
    }

    func templateApplicationScene(_ scene: CPTemplateApplicationScene, didDisconnect controller: CPInterfaceController) {
        Diag.log("carplay: disconnected")
        interface = nil
    }

    // MARK: location

    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        switch m.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse: m.requestLocation()
        case .denied, .restricted: showEmpty("Turn on Location for Charge & Chew to see chargers near you.")
        default: break
        }
    }

    func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        guard let loc = locs.last else { return }
        populate(around: loc)
    }

    func locationManager(_ m: CLLocationManager, didFailWithError error: Error) {
        showEmpty("Couldn't get a location fix.")
    }

    // MARK: content

    private func populate(around loc: CLLocation) {
        let hits = ChargerStore.shared.nearestWithFood(to: loc)
        Diag.log("carplay: \(hits.count) chargers with food near \(loc.coordinate.latitude),\(loc.coordinate.longitude)")
        guard !hits.isEmpty else { return showEmpty("No fast chargers with food within 40 miles.") }

        let items: [CPPointOfInterest] = hits.map { (c, dist) in
            let place = MKPlacemark(coordinate: c.coordinate)
            let item = MKMapItem(placemark: place)
            item.name = c.name
            let miles = dist / 1609.34
            let eats = c.food.prefix(3).map { "\($0.emoji) \($0.brand) \(walkMin($0.metres)) min" }.joined(separator: " · ")
            let p = CPPointOfInterest(location: item,
                                      title: c.name,
                                      subtitle: String(format: "%.1f mi · %d kW · %d stalls", miles, c.kw, c.stalls),
                                      summary: eats,
                                      detailTitle: c.name,
                                      detailSubtitle: "\(c.net) · \(c.city), \(c.st)",
                                      detailSummary: c.food.prefix(6).map { "\($0.emoji) \($0.brand) — \(walkMin($0.metres)) min walk" }.joined(separator: "\n"),
                                      pinImage: nil)
            p.primaryButton = CPTextButton(title: "Directions", textStyle: .confirm) { _ in
                item.openInMaps(launchOptions: [MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving])
            }
            p.userInfo = c.id
            return p
        }
        poi.setPointsOfInterest(items, selectedIndex: NSNotFound)
    }

    /// Same constant and the same rounding as the web app's walkMin(): a stop must not say
    /// "4 min" on the phone and "5 min" on the car.
    private func walkMin(_ metres: Double) -> Int { max(1, Int((metres / 80).rounded())) }

    private func showEmpty(_ message: String) {
        let info = CPInformationTemplate(title: "Charge & Chew", layout: .leading,
                                         items: [CPInformationItem(title: nil, detail: message)], actions: [])
        interface?.setRootTemplate(info, animated: false, completion: nil)
    }
}

extension CarPlaySceneDelegate: CPPointOfInterestTemplateDelegate {
    func pointOfInterestTemplate(_ t: CPPointOfInterestTemplate, didChangeMapRegion region: MKCoordinateRegion) {
        // Re-query around the map centre when the driver pans the car map.
        populate(around: CLLocation(latitude: region.center.latitude, longitude: region.center.longitude))
    }
    func pointOfInterestTemplate(_ t: CPPointOfInterestTemplate, didSelectPointOfInterest p: CPPointOfInterest) {}
}
