#import <CoreBluetooth/CoreBluetooth.h>
#import <Foundation/Foundation.h>

@interface LeshyAdvertisingFixture : NSObject <CBPeripheralManagerDelegate>
@property(nonatomic, copy) NSString *label;
@property(nonatomic, strong) CBPeripheralManager *manager;
- (instancetype)initWithLabel:(NSString *)label;
@end

@implementation LeshyAdvertisingFixture

- (instancetype)initWithLabel:(NSString *)label {
    self = [super init];
    if (self != nil) {
        _label = [label copy];
        _manager = [[CBPeripheralManager alloc] initWithDelegate:self
                                                            queue:dispatch_get_main_queue()];
    }
    return self;
}

- (void)emitState:(NSString *)state error:(NSString *)error {
    NSMutableDictionary *record = [@{
        @"schema": @"leshy.hil.macos_ble_name_fixture.v1",
        @"state": state,
        @"label": self.label,
        @"pid": @([[NSProcessInfo processInfo] processIdentifier]),
    } mutableCopy];
    if (error != nil) {
        record[@"error"] = error;
    }
    NSData *data = [NSJSONSerialization dataWithJSONObject:record
                                                   options:NSJSONWritingSortedKeys
                                                     error:nil];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:
        [NSData dataWithBytes:"\n" length:1]];
}

- (void)peripheralManagerDidUpdateState:(CBPeripheralManager *)peripheral {
    switch (peripheral.state) {
    case CBManagerStatePoweredOn:
        [peripheral startAdvertising:@{CBAdvertisementDataLocalNameKey: self.label}];
        break;
    case CBManagerStateUnknown:
        [self emitState:@"unknown" error:nil];
        break;
    case CBManagerStateResetting:
        [self emitState:@"resetting" error:nil];
        break;
    case CBManagerStateUnsupported:
        [self emitState:@"unsupported" error:nil];
        exit(2);
    case CBManagerStateUnauthorized:
        [self emitState:@"unauthorized" error:nil];
        exit(3);
    case CBManagerStatePoweredOff:
        [self emitState:@"powered_off" error:nil];
        break;
    }
}

- (void)peripheralManagerDidStartAdvertising:(CBPeripheralManager *)peripheral
                                        error:(NSError *)error {
    if (error != nil) {
        [self emitState:@"failed" error:error.localizedDescription];
        exit(5);
    }
    [self emitState:@"advertising" error:nil];
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) {
            fprintf(stderr, "usage: macos_ble_name_fixture LABEL\n");
            return 64;
        }
        NSString *label = [NSString stringWithUTF8String:argv[1]];
        NSUInteger bytes = [label lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        if (bytes < 1 || bytes > 29) {
            fprintf(stderr, "LABEL must occupy 1..29 UTF-8 bytes\n");
            return 64;
        }
        LeshyAdvertisingFixture *fixture =
            [[LeshyAdvertisingFixture alloc] initWithLabel:label];
        (void)fixture;
        [[NSRunLoop mainRunLoop] run];
    }
    return 0;
}
