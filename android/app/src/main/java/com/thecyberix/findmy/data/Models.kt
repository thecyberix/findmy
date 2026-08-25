package com.thecyberix.findmy.data

import kotlinx.serialization.Serializable

@Serializable
data class LocationFix(
    val latitude: Double? = null,
    val longitude: Double? = null,
    val timestamp: String? = null,
    val battery: String? = null,
)

@Serializable
data class Accessory(
    val id: String,
    val name: String,
    val battery: String = "Unknown",
    val location: LocationFix? = null,
    val _json: String? = null,
)

@Serializable
data class TwoFactorMethod(
    val index: Int,
    val type: String,
    val label: String,
    val phone: String? = null,
)

@Serializable
data class BridgeResponse(
    val ok: Boolean = false,
    val error: String? = null,
    val needs_2fa: Boolean = false,
    val logged_in: Boolean = false,
    val methods: List<TwoFactorMethod> = emptyList(),
    val accessories: List<Accessory>? = null,
    val accessory: Accessory? = null,
    val account: kotlinx.serialization.json.JsonElement? = null,
)
