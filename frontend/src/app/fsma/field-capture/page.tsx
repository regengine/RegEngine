import { FieldCaptureClient } from '@/components/mobile/FieldCaptureClient';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';

export default function FSMAFieldCapturePage() {
  if (!experimentalFeaturesEnabled()) {
    return (
      <FeatureNotEnabled
        featureName="Field Capture"
        backHref="/dashboard"
        backLabel="Back to dashboard"
      />
    );
  }
  return <FieldCaptureClient />;
}
