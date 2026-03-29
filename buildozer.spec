[app]

title = Webhook 推送工具
package.name = webhookpusher
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = assets/*,images/*.png,images/*.jpg
version = 1.0.0
requirements = python3,kivy,requests,plyer
android.api = 33
android.minapi = 21
android.sdk = 33
android.ndk = 25b
android.ndk_api = 21
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.accept_sdk_license = True
android.entrypoint = org.kivy.android.PythonActivity
android.allow_backup = True
android.arch = armeabi-v7a,arm64-v8a
android.api = 33
android.ndk = 25b
p4a.source_dir = ../python-for-android
p4a.bootstrap = sdl2
p4a.local_recipes = 
p4a.recipes = kivy,requests,plyer,openssl3

orientation = portrait
fullscreen = 0
android.mainclass = org.kivy.android.PythonActivity
android.service = True
android.wakelock = True
android.meta_data = 
android.add_src = 

[buildozer]
log_level = 2
warn_on_root = 1

