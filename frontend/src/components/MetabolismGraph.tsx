import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

mermaid.initialize({
  startOnLoad: true,
  theme: 'dark',
  securityLevel: 'strict',
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: 'basis',
  },
});

const MetabolismGraph: React.FC = () => {
  const mermaidRef = useRef<HTMLDivElement>(null);
  const [activeNode, setActiveNode] = useState<string | null>(null);

  // Simulation of the ATCG-M cycle
  useEffect(() => {
    const nodes = ['A', 'M1', 'T', 'M2', 'C', 'G'];
    let currentIndex = 0;

    const interval = setInterval(() => {
      setActiveNode(nodes[currentIndex]);
      currentIndex = (currentIndex + 1) % nodes.length;
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let isMounted = true;

    if (mermaidRef.current) {
      const graphDefinition = `
        graph LR
          A[Aggregator] --> M1{Membrane}
          M1 --> T[Transformer]
          T --> M2{Membrane}
          M2 --> C[Connector]
          C --> G[Generator]

          style A fill:${activeNode === 'A' ? '#00f2ff' : '#1f2937'},stroke:${activeNode === 'A' ? '#00f2ff' : '#374151'},stroke-width:2px
          style M1 fill:${activeNode === 'M1' ? '#bc13fe' : '#1f2937'},stroke:${activeNode === 'M1' ? '#bc13fe' : '#374151'},stroke-width:2px
          style T fill:${activeNode === 'T' ? '#00f2ff' : '#1f2937'},stroke:${activeNode === 'T' ? '#00f2ff' : '#374151'},stroke-width:2px
          style M2 fill:${activeNode === 'M2' ? '#bc13fe' : '#1f2937'},stroke:${activeNode === 'M2' ? '#bc13fe' : '#374151'},stroke-width:2px
          style C fill:${activeNode === 'C' ? '#00f2ff' : '#1f2937'},stroke:${activeNode === 'C' ? '#00f2ff' : '#374151'},stroke-width:2px
          style G fill:${activeNode === 'G' ? '#bc13fe' : '#1f2937'},stroke:${activeNode === 'G' ? '#bc13fe' : '#374151'},stroke-width:2px

          classDef pulse animation:pulse 2s infinite;
          ${activeNode ? `class ${activeNode} pulse` : ''}
      `;

      mermaid.render('mermaid-graph', graphDefinition).then((result) => {
        if (isMounted && mermaidRef.current) {
          mermaidRef.current.innerHTML = result.svg;
        }
      });
    }

    return () => {
      isMounted = false;
    };
  }, [activeNode]);

  return (
    <Card className="bg-card-bg border-gray-700">
      <CardHeader>
        <CardTitle className="text-cyberpunk-blue text-lg">Hive Metabolism (ATCG-M)</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          ref={mermaidRef}
          className="flex justify-center items-center p-4 min-h-[200px]"
        />
        <style dangerouslySetInnerHTML={{ __html: `
          @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.05); opacity: 0.8; }
            100% { transform: scale(1); opacity: 1; }
          }
          .pulse {
            animation: pulse 1s infinite;
          }
        `}} />
      </CardContent>
    </Card>
  );
};

export default MetabolismGraph;
