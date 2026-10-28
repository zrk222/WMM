#import "EngineBootstrap.h"
#import <Python/Python.h>

// Accessed only under the class monitor and Python GIL. Handles carry no authority.
static PyObject *WMMRuntimes = NULL;

static void WMMVerifierDestroy(PyObject *capsule) {
    void *retained = PyCapsule_GetPointer(capsule, "wmm.native.identity");
    if (retained) CFRelease(retained);
}

static PyObject *WMMVerifyIdentity(PyObject *capsule, PyObject *argument) {
    Py_ssize_t size = 0;
    const char *bytes = PyUnicode_AsUTF8AndSize(argument, &size);
    if (!bytes || size != 36) {
        PyErr_Clear();
        PyErr_SetString(PyExc_PermissionError, "A current native session is required");
        return NULL;
    }
    void *retained = PyCapsule_GetPointer(capsule, "wmm.native.identity");
    if (!retained) return NULL;
    WMMNativeIdentityVerifier verifier = (__bridge WMMNativeIdentityVerifier)retained;
    NSString *session = [[NSString alloc] initWithBytes:bytes length:(NSUInteger)size encoding:NSUTF8StringEncoding];
    NSDictionary *value = verifier(session);
    if (!value) Py_RETURN_NONE;
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
    if (!data || data.length > 4096) {
        PyErr_SetString(PyExc_PermissionError, "Native identity metadata is unavailable");
        return NULL;
    }
    PyObject *json = PyImport_ImportModule("json");
    PyObject *text = PyUnicode_DecodeUTF8(data.bytes, (Py_ssize_t)data.length, "strict");
    PyObject *result = json && text ? PyObject_CallMethod(json, "loads", "O", text) : NULL;
    Py_XDECREF(text); Py_XDECREF(json);
    return result;
}

static void WMMVaultDestroy(PyObject *capsule) {
    void *retained = PyCapsule_GetPointer(capsule, "wmm.native.vault");
    if (retained) CFRelease(retained);
}
static PyObject *WMMVaultInvoke(PyObject *capsule, PyObject *argument) {
    if (!PyBytes_Check(argument) || PyBytes_Size(argument) < 1 || PyBytes_Size(argument) > 8192) {
        PyErr_SetString(PyExc_ValueError, "Invalid protected storage request"); return NULL;
    }
    void *retained = PyCapsule_GetPointer(capsule, "wmm.native.vault");
    if (!retained) return NULL;
    WMMNativeVaultCallback callback = (__bridge WMMNativeVaultCallback)retained;
    NSData *request = [NSData dataWithBytes:PyBytes_AsString(argument) length:(NSUInteger)PyBytes_Size(argument)];
    NSData *result = callback(request);
    if (!result || result.length > 8192) {
        PyErr_SetString(PyExc_ValueError, "Protected storage unavailable"); return NULL;
    }
    return PyBytes_FromStringAndSize(result.bytes, (Py_ssize_t)result.length);
}
static PyMethodDef WMMVaultMethod = {"native_protected_storage", WMMVaultInvoke, METH_O,
    "Trusted native protected storage callback"};

static PyMethodDef WMMVerifierMethod = {"verify_native_identity", WMMVerifyIdentity, METH_O,
                                      "Recheck the native session and protected principal."};

static NSData *WMMResultBytes(PyObject *value, NSError **error) {
    NSData *result = nil;
    if (value && PyBytes_Check(value)) {
        Py_ssize_t length = PyBytes_Size(value);
        if (length > 0 && length <= 16777216)
            result = [NSData dataWithBytes:PyBytes_AsString(value) length:(NSUInteger)length];
    }
    if (!result) {
        PyErr_Clear();
        if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:4
            userInfo:@{NSLocalizedDescriptionKey: @"The operation was denied or could not finish. Saved state must be read back before retrying."}];
    }
    return result;
}

@implementation EngineBootstrap
+ (NSData *)inventoryWithError:(NSError **)error {
    @synchronized(self) {
        static BOOL startupFailed = NO;
        if (startupFailed) {
            if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:2 userInfo:nil];
            return nil;
        }
        if (!Py_IsInitialized()) {
            NSString *base = NSBundle.mainBundle.resourcePath;
            PyPreConfig preconfig;
            PyPreConfig_InitIsolatedConfig(&preconfig);
            preconfig.utf8_mode = 1;
            PyStatus status = Py_PreInitialize(&preconfig);
            if (PyStatus_Exception(status)) {
                if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:1 userInfo:nil];
                return nil;
            }
            PyConfig config;
            PyConfig_InitIsolatedConfig(&config);
            config.write_bytecode = 0;
            config.buffered_stdio = 0;
            config.install_signal_handlers = 0;
            status = PyConfig_SetBytesString(&config, &config.home,
                [[base stringByAppendingPathComponent:@"python"] UTF8String]);
            if (!PyStatus_Exception(status)) {
                status = Py_InitializeFromConfig(&config);
            }
            PyConfig_Clear(&config);
            if (PyStatus_Exception(status)) {
                if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:1
                    userInfo:@{NSLocalizedDescriptionKey: @"The bundled Python engine could not initialize."}];
                return nil;
            }
            NSString *app = [base stringByAppendingPathComponent:@"app"];
            PyObject *path = PyUnicode_FromString(app.UTF8String);
            if (!path || PyList_Insert(PySys_GetObject("path"), 0, path) != 0) {
                Py_XDECREF(path);
                PyErr_Clear();
                startupFailed = YES;
                PyEval_SaveThread();
                if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:2 userInfo:nil];
                return nil;
            }
            Py_DECREF(path);
            PyEval_SaveThread();
        }
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *policy = PyImport_ImportModule("mission_control.ios_runtime_policy");
        PyObject *activated = policy ? PyObject_CallMethod(policy, "activate", NULL) : NULL;
        if (!activated) startupFailed = YES;
        PyObject *module = activated ? PyImport_ImportModule("mission_control.ios_capabilities") : NULL;
        PyObject *value = module ? PyObject_CallMethod(module, "inventory", NULL) : NULL;
        PyObject *common = value ? PyImport_ImportModule("mission_control.common") : NULL;
        PyObject *encoded = common ? PyObject_CallMethod(common, "canonical", "O", value) : NULL;
        Py_ssize_t length = 0;
        const char *bytes = encoded ? PyUnicode_AsUTF8AndSize(encoded, &length) : NULL;
        NSData *result = bytes ? [NSData dataWithBytes:bytes length:(NSUInteger)length] : nil;
        if (!result) {
            // Do not expose a Python traceback containing workspace paths or data.
            PyErr_Clear();
            if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:3
                userInfo:@{NSLocalizedDescriptionKey: @"The bundled domain inventory could not load."}];
        }
        Py_XDECREF(encoded); Py_XDECREF(common); Py_XDECREF(value); Py_XDECREF(module);
        Py_XDECREF(activated); Py_XDECREF(policy);
        PyGILState_Release(gil);
        return result;
    }
}

+ (NSString *)openDatabase:(NSURL *)database verifier:(WMMNativeIdentityVerifier)verifier vault:(WMMNativeVaultCallback)vault error:(NSError **)error {
    @synchronized(self) {
        if (!database.isFileURL || !database.path.isAbsolutePath || !verifier || !vault || ![self inventoryWithError:error])
            return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        void *retained = CFBridgingRetain([verifier copy]);
        PyObject *capsule = PyCapsule_New(retained, "wmm.native.identity", WMMVerifierDestroy);
        if (!capsule) CFRelease(retained);
        PyObject *callback = capsule ? PyCFunction_New(&WMMVerifierMethod, capsule) : NULL;
        PyObject *module = callback ? PyImport_ImportModule("mission_control.ios_host") : NULL;
        PyObject *type = module ? PyObject_GetAttrString(module, "Runtime") : NULL;
        void *vaultRetained = CFBridgingRetain([vault copy]);
        PyObject *vaultCapsule = PyCapsule_New(vaultRetained, "wmm.native.vault", WMMVaultDestroy);
        if (!vaultCapsule) CFRelease(vaultRetained);
        PyObject *vaultCallback = vaultCapsule ? PyCFunction_New(&WMMVaultMethod, vaultCapsule) : NULL;
        PyObject *runtime = type && vaultCallback ? PyObject_CallFunction(type, "sOO", database.path.UTF8String, callback, vaultCallback) : NULL;
        Py_XDECREF(vaultCallback); Py_XDECREF(vaultCapsule);
        if (!WMMRuntimes) WMMRuntimes = PyDict_New();
        NSString *handle = NSUUID.UUID.UUIDString;
        if (!runtime || !WMMRuntimes || PyDict_SetItemString(WMMRuntimes, handle.UTF8String, runtime) != 0) {
            PyErr_Clear(); handle = nil;
            if (error) *error = [NSError errorWithDomain:@"WMM.Engine" code:5
                userInfo:@{NSLocalizedDescriptionKey: @"The protected local workspace could not open."}];
        }
        Py_XDECREF(runtime); Py_XDECREF(type); Py_XDECREF(module); Py_XDECREF(callback); Py_XDECREF(capsule);
        PyGILState_Release(gil);
        return handle;
    }
}

+ (NSData *)ownerCall:(NSString *)handle session:(NSString *)session request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *payload = request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        // One fixed dispatch, with no speculative call or automatic retry.
        PyObject *value = runtime && payload ? PyObject_CallMethod(runtime, "owner_call", "sO", session.UTF8String, payload) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(payload);
        PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)createWorkspace:(NSString *)handle session:(NSString *)session request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *payload = request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && payload ? PyObject_CallMethod(runtime, "create_workspace", "sO", session.UTF8String, payload) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(payload);
        PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)enroll:(NSString *)handle session:(NSString *)session appID:(NSString *)appID error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *value = runtime ? PyObject_CallMethod(runtime, "enroll", "ss", session.UTF8String, appID.UTF8String) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)workspaces:(NSString *)handle session:(NSString *)session error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *value = runtime ? PyObject_CallMethod(runtime, "workspaces", "s", session.UTF8String) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)report:(NSString *)handle session:(NSString *)session appID:(NSString *)appID error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *value = runtime ? PyObject_CallMethod(runtime, "report", "ss", session.UTF8String, appID.UTF8String) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)uploadMedia:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
               filename:(NSString *)filename content:(NSData *)content request:(NSData *)request
             inspection:(NSData *)inspection error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL bounded = content.length > 0 && content.length <= 67108864 && request.length > 0 &&
            request.length <= 1048576 && inspection.length > 0 && inspection.length <= 16384;
        PyObject *raw = bounded ? PyBytes_FromStringAndSize(content.bytes, (Py_ssize_t)content.length) : NULL;
        PyObject *body = raw ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *proof = body ? PyBytes_FromStringAndSize(inspection.bytes, (Py_ssize_t)inspection.length) : NULL;
        PyObject *value = runtime && proof ? PyObject_CallMethod(runtime, "native_media_upload", "sssOOO",
            session.UTF8String, appID.UTF8String, filename.UTF8String, raw, body, proof) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(proof); Py_XDECREF(body); Py_XDECREF(raw);
        PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)mediaList:(NSString *)handle session:(NSString *)session appID:(NSString *)appID error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *value = runtime ? PyObject_CallMethod(runtime, "native_media_list", "ss", session.UTF8String, appID.UTF8String) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)reviewMedia:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                mediaID:(NSString *)mediaID request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *body = request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_media_review", "sssO",
            session.UTF8String, appID.UTF8String, mediaID.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)production:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                 action:(NSString *)action request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL known = [@[@"prepare", @"validate", @"source"] containsObject:action];
        PyObject *body = known && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_production", "sssO",
            session.UTF8String, appID.UTF8String, action.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)agentAccess:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                 action:(NSString *)action request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL known = [@[@"list", @"issue", @"revoke"] containsObject:action];
        PyObject *body = known && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_agent_access", "sssO",
            session.UTF8String, appID.UTF8String, action.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)jobs:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
           action:(NSString *)action request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL known = [@[@"queue", @"run", @"monitor", @"cancel"] containsObject:action];
        PyObject *body = known && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_jobs", "sssO",
            session.UTF8String, appID.UTF8String, action.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)providers:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                action:(NSString *)action request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL known = [@[@"view", @"save", @"disconnect", @"cleanup"] containsObject:action];
        PyObject *body = known && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_providers", "sssO",
            session.UTF8String, appID.UTF8String, action.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (NSData *)agentCall:(NSString *)handle session:(NSString *)session credential:(NSString *)credential
               request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        PyObject *body = credential.length == 48 && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_agent_call", "ssO",
            session.UTF8String, credential.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}

+ (void)close:(NSString *)handle {
    @synchronized(self) {
        if (!Py_IsInitialized()) return;
        PyGILState_STATE gil = PyGILState_Ensure();
        if (WMMRuntimes && PyDict_DelItemString(WMMRuntimes, handle.UTF8String) != 0) PyErr_Clear();
        PyGILState_Release(gil);
    }
}

+ (NSData *)inference:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                action:(NSString *)action request:(NSData *)request error:(NSError **)error {
    @synchronized(self) {
        if (![self inventoryWithError:error]) return nil;
        PyGILState_STATE gil = PyGILState_Ensure();
        PyObject *runtime = WMMRuntimes ? PyDict_GetItemString(WMMRuntimes, handle.UTF8String) : NULL;
        BOOL known = [@[@"prepare", @"start", @"run", @"read", @"history", @"mode"] containsObject:action];
        PyObject *body = known && request.length > 0 && request.length <= 1048576
            ? PyBytes_FromStringAndSize(request.bytes, (Py_ssize_t)request.length) : NULL;
        PyObject *value = runtime && body ? PyObject_CallMethod(runtime, "native_inference", "sssO",
            session.UTF8String, appID.UTF8String, action.UTF8String, body) : NULL;
        NSData *result = WMMResultBytes(value, error);
        Py_XDECREF(value); Py_XDECREF(body); PyGILState_Release(gil);
        return result;
    }
}
@end
