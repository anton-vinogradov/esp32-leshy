#import <CoreWLAN/CoreWLAN.h>
#import <Foundation/Foundation.h>

// Targeted, read-only scan used by the physical Web HIL.  It deliberately
// emits no network identity: callers receive only visible/not-visible status.
int main(int argc, const char* argv[]) {
    @autoreleasepool {
        if (argc != 3) return 64;
        NSString* interfaceName = [NSString stringWithUTF8String:argv[1]];
        NSString* expectedName = [NSString stringWithUTF8String:argv[2]];
        if (interfaceName.length == 0 || expectedName.length == 0) return 65;
        CWInterface* interface =
            [[CWWiFiClient sharedWiFiClient] interfaceWithName:interfaceName];
        if (interface == nil) return 65;
        NSError* error = nil;
        NSSet<CWNetwork*>* networks =
            [interface scanForNetworksWithName:expectedName error:&error];
        if (error != nil || networks == nil) return 2;
        return networks.count == 0 ? 1 : 0;
    }
}
