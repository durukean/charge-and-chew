import UIKit
import CoreLocation
import CarPlay

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {

    func application(_ app: UIApplication,
                     didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        Diag.reset()          // first thing: everything below is part of this launch's log
        // Before ANY reader resolves data.js: after an app update the bundle may be newer
        // than a copy downloaded earlier, and every reader prefers the overlay.
        DataUpdater.pruneStaleOverlay(
            bundled: Bundle.main.url(forResource: "Web", withExtension: nil)?.appendingPathComponent("data.js"))
        ChargerStore.shared.dataURL = {
            let overlay = DataUpdater.overlayDir.appendingPathComponent("data.js")
            if FileManager.default.fileExists(atPath: overlay.path) { return overlay }
            return Bundle.main.url(forResource: "Web", withExtension: nil)?.appendingPathComponent("data.js")
        }
        #if DEBUG
        // Exercise the Siri answer with real data at launch; Shortcuts cannot run an app
        // intent in the Simulator, so this is how the intent's logic gets verified.
        if ProcessInfo.processInfo.environment["CC_TEST_INTENT"] != nil {
            DispatchQueue.global(qos: .utility).async {
                let store = StopAnswer.preparedStore()
                for (label, loc, chain) in [
                    ("LA, no chain", CLLocation(latitude: 34.0522, longitude: -118.2437), String?.none),
                    ("LA, IHOP", CLLocation(latitude: 34.0522, longitude: -118.2437), "IHOP"),
                    ("LA, Zzzz", CLLocation(latitude: 34.0522, longitude: -118.2437), "Zzzz"),
                    ("mid-ocean", CLLocation(latitude: 30.0, longitude: -140.0), String?.none),
                ] {
                    let r = StopAnswer.build(near: loc, chain: chain, store: store)
                    Diag.log("INTENT[\(label)]: \(r.spoken)")
                }
                Diag.log("INTENT[no location]: \(StopAnswer.build(near: nil, chain: nil, store: store).spoken)")
            }
        }
        #endif
        return true
    }

    /// Scene delegates are chosen HERE, by type. An earlier build resolved the delegate by
    /// string through Info.plist and the lookup silently failed under Xcode 26's debug-dylib
    /// layout: the app launched, connected no scene, and showed a black window. Assigning
    /// the class directly cannot fail that way.
    func application(_ app: UIApplication, configurationForConnecting session: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let cfg = UISceneConfiguration(name: nil, sessionRole: session.role)
        if session.role == .carTemplateApplication {
            cfg.delegateClass = CarPlaySceneDelegate.self
        } else {
            cfg.delegateClass = PhoneSceneDelegate.self
        }
        return cfg
    }
}
