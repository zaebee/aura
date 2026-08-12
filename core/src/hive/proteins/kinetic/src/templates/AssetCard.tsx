import React from 'react';
import {
  spring,
  interpolate,
  useCurrentFrame,
  useVideoConfig
} from 'remotion';

// Согласование с ДНК v0.3.1
interface Asset {
  identifier: string;
  name: string;
  description: string;
}

export const AssetCard: React.FC<{ asset: Asset }> = ({ asset }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Биологический пульс: цикл каждые 30 кадров
  const pulseFrame = frame % 30;

  const pulse = spring({
    frame: pulseFrame,
    fps,
    config: {
      damping: 10,
      stiffness: 100,
      mass: 0.5,
    },
  });

  // Интерполяция анимации
  const scale = interpolate(pulse, [0, 1], [1, 1.05]);
  const opacity = interpolate(pulse, [0, 1], [0.9, 1]);
  const glowRadius = interpolate(pulse, [0, 1], [10, 30]);

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#0a0a0f', // Deep Void
        color: '#e0e0e0',
        fontFamily: 'monospace',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '40px',
          border: '3px solid #00f0ff', // Cyan Membrane
          borderRadius: '20px',
          boxShadow: `0 0 ${glowRadius}px rgba(0, 240, 255, 0.4)`,
          transform: `scale(${scale})`,
          opacity: opacity,
          background: 'linear-gradient(145deg, #12121a, #0a0a0f)',
          maxWidth: '80%',
        }}
      >
        <div style={{
          fontSize: '1.2rem',
          color: '#00f0ff',
          letterSpacing: '0.2em',
          marginBottom: '10px',
          textTransform: 'uppercase'
        }}>
          Aura Verified Asset
        </div>

        <div style={{
          fontSize: '3rem',
          fontWeight: 'bold',
          marginBottom: '20px',
          textShadow: '0 0 10px rgba(255, 255, 255, 0.5)'
        }}>
          {asset.identifier}
        </div>

        <div style={{
          width: '100%',
          height: '2px',
          background: 'linear-gradient(90deg, transparent, #ff00aa, transparent)',
          marginBottom: '20px'
        }} />

        <div style={{ fontSize: '2rem', color: '#ffd700', marginBottom: '10px' }}>
          {asset.name}
        </div>

        <div style={{ fontSize: '1.2rem', color: '#888', textAlign: 'center' }}>
          {asset.description}
        </div>
      </div>
    </div>
  );
};
