import React from 'react';
import { Transformer } from '../dna';
import { JitUiRequest } from '../../lib/aura/negotiation/v1/negotiation_pb';
import { CheckCircle, XCircle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';

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
    const { templateId } = request;

    switch (templateId) {
      case 'high_value_confirm':
        return this.renderHighValueConfirm(request, actions);
      default:
        return this.renderDefaultTemplate(request, actions);
    }
  }

  /**
   * Render High Value Transaction Confirmation template.
   */
  private renderHighValueConfirm(request: JitUiRequest, actions: JITActions): React.ReactElement {
    const context = request.contextData || {};
    
    return (
      <Card className="bg-card-bg border-2 border-cyberpunk-purple">
        <CardHeader>
          <CardTitle className="text-cyberpunk-purple">High Value Transaction Confirmation</CardTitle>
          <CardDescription>This transaction requires your explicit approval</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-300">Item:</span>
              <Badge variant="secondary" className="bg-gray-700">
                {context.item_name || 'Unknown Item'}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-300">Amount:</span>
              <Badge variant="secondary" className="bg-gray-700">
                ${context.price || 'N/A'}
              </Badge>
            </div>
            {context.id && (
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-300">Item ID:</span>
                <Badge variant="secondary" className="bg-gray-700">
                  {context.id}
                </Badge>
              </div>
            )}
          </div>
          <div className="p-3 bg-yellow-900/20 border border-yellow-700 rounded-md">
            <p className="text-sm text-yellow-400 font-medium">⚠️ Attention Required</p>
            <p className="text-xs text-gray-300 mt-1">
              This transaction exceeds the autonomous decision threshold and requires your explicit approval.
            </p>
          </div>
        </CardContent>
        <CardFooter className="flex justify-end space-x-3">
          <Button 
            variant="destructive" 
            onClick={actions.onReject}
            className="bg-red-700 hover:bg-red-600"
          >
            <XCircle className="mr-2" size={16} />
            Reject
          </Button>
          <Button 
            onClick={actions.onApprove}
            className="bg-green-700 hover:bg-green-600"
          >
            <CheckCircle className="mr-2" size={16} />
            Approve
          </Button>
        </CardFooter>
      </Card>
    );
  }

  /**
   * Render Default/Fallback JIT template.
   */
  private renderDefaultTemplate(request: JitUiRequest, actions: JITActions): React.ReactElement {
    return (
      <Card className="bg-card-bg border border-gray-600">
        <CardHeader>
          <CardTitle className="text-cyberpunk-blue">Just-In-Time Decision</CardTitle>
          <CardDescription>Template: {request.templateId}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-3 bg-blue-900/20 border border-blue-700 rounded-md">
            <p className="text-sm text-blue-400">Context Data:</p>
            <pre className="text-xs text-gray-300 mt-2 overflow-x-auto">
              {JSON.stringify(request.contextData, null, 2)}
            </pre>
          </div>
        </CardContent>
        <CardFooter className="flex justify-end space-x-3">
          <Button variant="outline" onClick={actions.onReject}>
            <XCircle className="mr-2" size={16} />
            Reject
          </Button>
          <Button onClick={actions.onApprove}>
            <CheckCircle className="mr-2" size={16} />
            Approve
          </Button>
        </CardFooter>
      </Card>
    );
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
