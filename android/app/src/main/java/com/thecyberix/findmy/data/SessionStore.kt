package com.thecyberix.findmy.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class SessionStore(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context,
        "findmy_session",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    var email: String
        get() = prefs.getString("email", "") ?: ""
        set(value) { prefs.edit().putString("email", value).apply() }

    var accountJson: String?
        get() = prefs.getString("account", null)
        set(value) { prefs.edit().putString("account", value).apply() }

    var accessoriesJson: String
        get() = prefs.getString("accessories", "[]") ?: "[]"
        set(value) { prefs.edit().putString("accessories", value).apply() }

    var alertsEnabled: Boolean
        get() = prefs.getBoolean("alerts", false)
        set(value) { prefs.edit().putBoolean("alerts", value).apply() }

    fun clear() {
        prefs.edit().clear().apply()
    }
}
