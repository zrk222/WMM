#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
typedef NSDictionary<NSString *, id> * _Nullable (^WMMNativeIdentityVerifier)(NSString *session);
typedef NSData * _Nullable (^WMMNativeVaultCallback)(NSData *request);
/// Loads only bundled Python. No REPL, arbitrary script or remote code interface.
@interface EngineBootstrap : NSObject
+ (nullable NSData *)inventoryWithError:(NSError **)error NS_SWIFT_NAME(inventory());
+ (nullable NSString *)openDatabase:(NSURL *)database verifier:(WMMNativeIdentityVerifier)verifier vault:(WMMNativeVaultCallback)vault
                              error:(NSError **)error NS_SWIFT_NAME(open(database:verifier:vault:));
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
+ (nullable NSData *)production:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(production(handle:session:appID:action:request:));
+ (void)close:(NSString *)handle;
+ (nullable NSData *)insights:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(insights(handle:session:appID:action:request:));
+ (nullable NSData *)humanReview:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(humanReview(handle:session:appID:action:request:));
+ (void)reviewLogout:(NSString *)handle NS_SWIFT_NAME(reviewLogout(handle:));
+ (nullable NSData *)agentReview:(NSString *)handle session:(NSString *)session credential:(NSString *)credential
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(agentReview(handle:session:credential:action:request:));
+ (nullable NSData *)studio:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                     action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(studio(handle:session:appID:action:request:));
+ (nullable NSData *)studioFinish:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                           request:(NSData *)request inspection:(NSData *)inspection error:(NSError **)error
    NS_SWIFT_NAME(studioFinish(handle:session:appID:request:inspection:));
+ (nullable NSData *)studioSource:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                           request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(studioSource(handle:session:appID:request:));
+ (nullable NSData *)automation:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(automation(handle:session:appID:action:request:));
+ (nullable NSData *)evidenceForm:(NSString *)handle session:(NSString *)session appID:(NSString *)appID error:(NSError **)error
    NS_SWIFT_NAME(evidenceForm(handle:session:appID:));
+ (nullable NSData *)updateWorkspace:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                             request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(updateWorkspace(handle:session:appID:request:));
+ (nullable NSData *)inference:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(inference(handle:session:appID:action:request:));
+ (nullable NSData *)providers:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                         action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(providers(handle:session:appID:action:request:));
+ (nullable NSData *)jobs:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                    action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(jobs(handle:session:appID:action:request:));
+ (nullable NSData *)agentAccess:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                          action:(NSString *)action request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(agentAccess(handle:session:appID:action:request:));
+ (nullable NSData *)agentCall:(NSString *)handle session:(NSString *)session credential:(NSString *)credential
                       request:(NSData *)request error:(NSError **)error
    NS_SWIFT_NAME(agentCall(handle:session:credential:request:));
+ (nullable NSData *)snapshotExport:(NSString *)handle session:(NSString *)session appID:(NSString *)appID error:(NSError **)error
    NS_SWIFT_NAME(snapshotExport(handle:session:appID:));
+ (nullable NSData *)snapshotRestore:(NSString *)handle session:(NSString *)session appID:(NSString *)appID
                              request:(NSData *)request confirmed:(BOOL)confirmed error:(NSError **)error
    NS_SWIFT_NAME(snapshotRestore(handle:session:appID:request:confirmed:));
@end
NS_ASSUME_NONNULL_END
