package com.thecyberix.findmy.notify

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import com.thecyberix.findmy.R

object AlertNotifier {
    private const val CHANNEL = "findmy_alerts"

    fun notify(context: Context, title: String, body: String, id: Int) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "FindMy", NotificationManager.IMPORTANCE_DEFAULT),
        )
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build()
        manager.notify(id, notification)
    }
}
