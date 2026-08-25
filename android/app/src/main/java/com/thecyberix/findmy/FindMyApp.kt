package com.thecyberix.findmy

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.thecyberix.findmy.notify.DailyScheduler
import org.osmdroid.config.Configuration

class FindMyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        Configuration.getInstance().userAgentValue = packageName
        Configuration.getInstance().osmdroidBasePath = filesDir
        Configuration.getInstance().osmdroidTileCache = cacheDir
        DailyScheduler.schedule(this)
    }
}
