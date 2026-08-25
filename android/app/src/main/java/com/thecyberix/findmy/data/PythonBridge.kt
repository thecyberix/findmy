package com.thecyberix.findmy.data

import com.chaquo.python.Python
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

object PythonBridge {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Synchronized
    private fun call(name: String, vararg args: Any?): BridgeResponse {
        val py = Python.getInstance().getModule("bridge")
        val raw = py.callAttr(name, *args).toString()
        return json.decodeFromString(raw)
    }

    fun restore(accountJson: String, accessoriesJson: String): BridgeResponse =
        call("restore", accountJson, accessoriesJson)

    fun login(email: String, password: String): BridgeResponse = call("login", email, password)

    fun request2fa(index: Int): BridgeResponse = call("request_2fa", index)

    fun submit2fa(index: Int, code: String): BridgeResponse = call("submit_2fa", index, code)

    fun addAccessory(jsonText: String, fallbackName: String): BridgeResponse =
        call("add_accessory", jsonText, fallbackName)

    fun removeAccessory(id: String): BridgeResponse = call("remove_accessory", id)

    fun refresh(): BridgeResponse = call("refresh")

    fun logout(): BridgeResponse = call("logout")

    fun encodeAccessories(items: List<Accessory>): String = json.encodeToString(items)

    fun encodeAccount(element: kotlinx.serialization.json.JsonElement?): String? =
        element?.toString()
}
