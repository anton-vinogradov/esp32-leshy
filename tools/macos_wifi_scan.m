#import <CoreWLAN/CoreWLAN.h>
#import <Foundation/Foundation.h>

// Targeted, read-only scan used by the physical Web HIL.  It deliberately
// emits no network identity: callers receive only visible/not-visible status.
int main(int argc, const char* argv[]) {
    @autoreleasepool {
        if (argc < 4 || argc > 5) return 64;
        NSString* operation = [NSString stringWithUTF8String:argv[1]];
        NSString* interfaceName = [NSString stringWithUTF8String:argv[2]];
        NSString* expectedName = [NSString stringWithUTF8String:argv[3]];
        if (interfaceName.length == 0 || expectedName.length == 0) return 65;
        CWInterface* interface =
            [[CWWiFiClient sharedWiFiClient] interfaceWithName:interfaceName];
        if (interface == nil) return 65;
        NSError* error = nil;
        NSSet<CWNetwork*>* networks =
            [interface scanForNetworksWithName:expectedName error:&error];
        if (error != nil || networks == nil) return 2;
        if (networks.count == 0) return 1;
        if ([operation isEqualToString:@"scan"] && argc == 4) return 0;
        if (![operation isEqualToString:@"associate"] || argc != 5) return 64;
        NSString* passphrase = [NSString stringWithUTF8String:argv[4]];
        if (passphrase.length < 8) return 65;
        CWNetwork* network = networks.anyObject;
        // CoreWLAN is materially more reliable for a short-lived WPA AP when
        // the previous association is released explicitly. The caller owns a
        // captured snapshot and restores it in a fail-closed finally path.
        [interface disassociate];
        [NSThread sleepForTimeInterval:0.25];
        error = nil;
        BOOL associated = [interface associateToNetwork:network
                                                password:passphrase
                                                   error:&error];
        return associated && error == nil ? 0 : 3;
    }
}
