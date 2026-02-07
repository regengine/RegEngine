import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
    appId: 'com.regengine.app',
    appName: 'RegEngine',
    webDir: 'out',
    server: {
        androidScheme: 'https'
    }
};

export default config;
