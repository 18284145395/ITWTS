[app]

title = Webhook 推送工具
package.name = webhookpusher
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0
requirements = python3,kivy,requests,plyer,android.permissions
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True
android.entrypoint = org.kivy.android.PythonActivity
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
