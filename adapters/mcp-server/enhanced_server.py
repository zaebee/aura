"""
Enhanced Aura MCP Server with Mistral Vibe Integration

This enhanced server adds direct Mistral Vibe integration for advanced features
while maintaining full compatibility with the standard MCP server.
"""

import logging
import os
from typing import Any, Optional

from server import AuraMCPServer, logger
from mock_mcp import Tool


class EnhancedAuraMCPServer(AuraMCPServer):
    """Enhanced MCP Server with direct Mistral Vibe integration."""
    
    def __init__(self):
        """Initialize enhanced server with Mistral Vibe client."""
        super().__init__()
        self.mistral_client = self._initialize_mistral_client()
        
        if self.mistral_client:
            logger.info("🤖 Mistral Vibe integration enabled")
            self._register_enhanced_tools()
        else:
            logger.info("🤖 Mistral Vibe integration not available")
    
    def _initialize_mistral_client(self) -> Optional[Any]:
        """Initialize Mistral Vibe client if API key is available."""
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        
        if not mistral_api_key:
            logger.warning("MISTRAL_API_KEY not set, skipping Mistral Vibe integration")
            return None
        
        try:
            from langchain_mistralai import ChatMistralAI
            from llm_strategy import AI_Decision
            
            # Create Mistral client with same config as Core Service
            mistral_llm = ChatMistralAI(
                model_name="mistral-large-latest",
                temperature=0.2,
                api_key=mistral_api_key
            )
            
            return mistral_llm.with_structured_output(AI_Decision)
            
        except ImportError as e:
            logger.warning(f"Mistral Vibe client not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Mistral Vibe client: {e}")
            return None
    
    def _register_enhanced_tools(self):
        """Register enhanced tools with Mistral Vibe integration."""
        try:
            from mcp import Tool as RealTool
        except ImportError:
            from mock_mcp import Tool as RealTool
        
        # Enhanced search with AI insights
        self.mcp_server.register_tool(
            RealTool(
                name="enhanced_search",
                description="Search hotels with AI-powered insights and recommendations",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for hotels"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 3
                        },
                        "context": {
                            "type": "string",
                            "description": "Additional context for AI analysis",
                            "default": ""
                        }
                    },
                    "required": ["query"]
                },
                func=self.enhanced_search_with_insights
            )
        )
        
        logger.info("🛠️  Registered enhanced tool: enhanced_search")
    
    async def enhanced_search_with_insights(self, query: str, limit: int = 3, context: str = "") -> str:
        """
        Enhanced search with Mistral Vibe insights.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            context: Additional context for LLM analysis
            
        Returns:
            Search results with AI insights
        """
        if not self.mistral_client:
            return await self.search_hotels(query, limit)
        
        # Get standard search results
        search_results = await self.search_hotels(query, limit)
        
        # Get AI insights
        try:
            system_prompt = f"""Analyze these search results and provide insights:
            
            QUERY: {query}
            CONTEXT: {context}
            RESULTS: {search_results}
            
            Provide a concise analysis including:
            1. Summary of findings (1-2 sentences)
            2. Top recommendation
            3. Potential negotiation strategies
            """
            
            from langchain_core.prompts import ChatPromptTemplate
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "Provide your analysis.")
            ])
            
            chain = prompt | self.mistral_client
            insights = chain.invoke({})
            
            return f"{search_results}\n\n🤖 AI Insights:\n{insights.reasoning}"
            
        except Exception as e:
            logger.error(f"AI insights failed: {e}")
            return search_results


async def main():
    """Main entry point for enhanced server."""
    server = EnhancedAuraMCPServer()
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("🔘 Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        await server.shutdown()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())