import UIKit
import CarPlay

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {

    func application(_ app: UIApplication,
                     didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        ChargerStore.shared.dataURL = {
            let overlay = DataUpdater.overlayDir.appendingPathComponent("data.js")
            if FileManager.default.fileExists(atPath: overlay.path) { return overlay }
            return Bundle.main.url(forResource: "Web", withExtension: nil)?.appendingPathComponent("data.js")
        }
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
