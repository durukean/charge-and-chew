import UIKit

/// The phone window. Scenes came back for CarPlay's sake -- a CarPlay app must be scene
/// based -- but the delegate is assigned by TYPE in AppDelegate.configurationForConnecting,
/// never by the string lookup in Info.plist that silently failed before.
final class PhoneSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let ws = scene as? UIWindowScene else { return }
        let w = UIWindow(windowScene: ws)
        w.rootViewController = WebViewController()
        w.makeKeyAndVisible()
        window = w
    }
}
