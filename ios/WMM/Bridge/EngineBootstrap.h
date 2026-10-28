#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
/// Loads only bundled Python. No REPL, arbitrary script or remote code interface.
@interface EngineBootstrap : NSObject
+ (nullable NSData *)inventoryWithError:(NSError **)error NS_SWIFT_NAME(inventory());
@end
NS_ASSUME_NONNULL_END
