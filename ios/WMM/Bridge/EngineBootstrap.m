#import "EngineBootstrap.h"
#import <Python/Python.h>

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
@end
