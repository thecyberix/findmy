package com.thecyberix.findmy.notify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.thecyberix.findmy.data.PythonBridge
import com.thecyberix.findmy.data.SessionStore
import java.time.Instant
import java.time.temporal.ChronoUnit
import kotlin.concurrent.thread

class DailyCheckReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        DailyScheduler.schedule(context)
        val pending = goAsync()
        thread {
            try {
                runCheck(context.applicationContext)
            } finally {
                pending.finish()
            }
        }
    }

    private fun runCheck(context: Context) {
        val store = SessionStore(context)
        if (!store.alertsEnabled) return
        val account = store.accountJson ?: return
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        val restored = PythonBridge.restore(account, store.accessoriesJson)
        if (!restored.ok) return
        val result = PythonBridge.refresh()
        if (!result.ok) return
        val accessories = result.accessories ?: return
        store.accessoriesJson = PythonBridge.encodeAccessories(accessories)
        val now = Instant.now()
        accessories.forEachIndexed { index, tag ->
            if (tag.battery.equals("Very Low", ignoreCase = true)) {
                AlertNotifier.notify(context, tag.name, "Very low battery", 100 + index)
            }
            val stamp = tag.location?.timestamp?.let { runCatching { Instant.parse(it) }.getOrNull() }
            val missing = stamp == null || ChronoUnit.HOURS.between(stamp, now) >= 24
            if (missing) {
                AlertNotifier.notify(context, tag.name, "No report for over a day", 200 + index)
            }
        }
    }
}
