import React from 'react';
import { Transformer } from '../dna';
import { JitUiRequest } from '../../lib/aura/negotiation/v1/negotiation_pb';
import { NegotiationView } from '../chambers/negotiation/V';

interface JITActions {
  onApprove: () => void;
  onReject: () => void;
}

/**
 * JIT UI Engine - Transforms JitUiRequest into React components.
 */
export class JITTransformer implements Transformer {
  /**
   * Transforms a request context into a rendered JIT UI.
   */
  async think(context: { request: JitUiRequest; actions: JITActions }): Promise<React.ReactElement> {
    const { request, actions } = context;
    
    // In the future, we will resolve the chamber based on the request metadata.
    // For now, we delegate to the negotiation chamber's View (V).
    return <NegotiationView request={request} actions={actions} />;
  }
}

/**
 * React Component Wrapper for the JIT Engine.
 */
export function JITRenderer({
  request,
  onApprove,
  onReject
}: {
  request: JitUiRequest,
  onApprove: () => void,
  onReject: () => void
}) {
  const [content, setContent] = React.useState<React.ReactElement | null>(null);
  const transformer = React.useMemo(() => new JITTransformer(), []);

  React.useEffect(() => {
    transformer.think({ request, actions: { onApprove, onReject } }).then((element) => {
      setContent(element as React.ReactElement);
    });
  }, [request, onApprove, onReject, transformer]);

  if (!content) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-2xl animate-fade-in">
        {content}
      </div>
    </div>
  );
}
