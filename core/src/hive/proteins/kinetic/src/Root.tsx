import React from 'react';
import { Composition } from 'remotion';
import { AssetCard } from './templates/AssetCard';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="VisionReport"
        component={AssetCard}
        durationInFrames={150}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          asset: {
            identifier: "PREVIEW-MODE",
            name: "System Asset",
            description: "Awaiting metabolic injection..."
          }
        }}
      />
    </>
  );
};
