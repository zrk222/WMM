#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
typedef NSDictionary<NSString *, id> * _Nullable (^WMMNativeIdentityVerifier)(NSString *session);
/// Loads only bundled Python. No REPL, arbitrary script or remote code interface.
@interface EngineBootstrap : NSObject
+ (nullable NSData *)inventoryWithError:(NSError **)error NS_SWIFT_NAME(inventory());
+ (nullable NSString *)openDatabase:(NSURL *)database verifier:(WMMNativeIdentityVerifier)verifier
                              error:(NSError **)error NS_SWIFT_NAME(open(database:verifier:));
+ (nullable NSData *)ownerCall:(NSString *)handle session:(NSString *)session request:(NSData *)request
                         error:(NSError **)error NS_SWIFT_NAME(ownerCall(handle:session:request:));
+ (nullable NSData *)createWorkspace:(NSString *)handle session:(NSString *)session request:(NSData *)request
                               error:(NSError **)error NS_SWIFT_NAME(createWorkspace(handle:session:request:));
+ (nullable NSData *)enroll:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                      error:(NSError **)error NS_SWIFT_NAME(enroll(handle:session:appID:));
+ (nullable NSData *)workspaces:(NSString *)handle session:(NSString *)session
                          error:(NSError **)error NS_SWIFT_NAME(workspaces(handle:session:));
+ (nullable NSData *)report:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                      error:(NSError **)error NS_SWIFT_NAME(report(handle:session:appID:));
+ (nullable NSData *)uploadMedia:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                       filename:(NSString *)filename content:(NSData *)content request:(NSData *)request
                     inspection:(NSData *)inspection error:(NSError **)error
    NS_SWIFT_NAME(uploadMedia(handle:session:appID:filename:content:request:inspection:));
+ (nullable NSData *)mediaList:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         error:(NSError **)error NS_SWIFT_NAME(mediaList(handle:session:appID:));
+ (nullable NSData *)reviewMedia:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                        mediaID:(NSString *)mediaID request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(reviewMedia(handle:session:appID:mediaID:request:));
+ (void)close:(NSString *)handle;
@end
NS_ASSUME_NONNULL_END
