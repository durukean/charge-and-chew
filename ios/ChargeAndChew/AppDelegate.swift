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
        // Give the widget the same data. Cheap (one 4 MB copy, only when the source is newer)
        // and off the main thread, so launch is not paying for it.
        DispatchQueue.global(qos: .utility).async {
            guard let src = ChargerStore.shared.dataURL?(), let dir = ChargerStore.groupDir else { return }
            let dst = dir.appendingPathComponent("data.js")
            let fm = FileManager.default
            let srcDate = (try? fm.attributesOfItem(atPath: src.path)[.modificationDate] as? Date) ?? .distantPast
            let dstDate = (try? fm.attributesOfItem(atPath: dst.path)[.modificationDate] as? Date) ?? .distantPast
            if !fm.fileExists(atPath: dst.path) || srcDate > dstDate {
                try? fm.removeItem(at: dst)
                try? fm.copyItem(at: src, to: dst)
            }
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
