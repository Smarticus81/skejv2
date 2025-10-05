# AGENTS.md - LiveKit Voice Pipeline Agent Guide

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Agent Lifecycle](#agent-lifecycle)
- [Building Custom Agents](#building-custom-agents)
- [Multi-Agent Workflows](#multi-agent-workflows)
- [Tool Development](#tool-development)
- [State Management](#state-management)
- [Advanced Patterns](#advanced-patterns)
- [Performance Optimization](#performance-optimization)
- [Testing Agents](#testing-agents)

---

## Architecture Overview

### Voice Pipeline Architecture

```
┌─────────────┐
│   User      │
│   Audio     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                    LiveKit Room                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐      │
│  │   STT    │ -> │   LLM    │ -> │     TTS      │      │
│  │ Assembly │    │ GPT-4.1  │    │  Cartesia    │      │
│  │   AI     │    │   mini   │    │   Sonic-2    │      │
│  └──────────┘    └────┬─────┘    └──────────────┘      │
│                       │                                  │
│                       ▼                                  │
│              ┌────────────────┐                         │
│              │  Function      │                         │
│              │  Tools/MCP     │                         │
│              └────────┬───────┘                         │
│                       │                                  │
│                       ▼                                  │
│              ┌────────────────┐                         │
│              │   Database/    │                         │
│              │   External     │                         │
│              │   Services     │                         │
│              └────────────────┘                         │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│   Agent     │
│   Audio     │
└─────────────┘
```

### Component Responsibilities

**AgentSession:**
- Orchestrates STT-LLM-TTS pipeline
- Manages conversation context
- Handles turn detection
- Provides tool execution framework

**Worker:**
- Manages multiple job processes
- Load balancing and health monitoring
- Resource management
- Graceful shutdown handling

**Job:**
- Single conversation session
- Isolated process per conversation
- Room connection management
- Lifecycle from connection to cleanup

---

## Agent Lifecycle

### 1. Initialization Phase

```python
async def entrypoint(ctx: JobContext):
    """Agent entrypoint - called when job is assigned"""
    
    # 1. Initialize configuration
    config = VoicePipelineConfig()
    
    # 2. Create agent session
    session = AgentSession(
        stt=config.stt_model,
        llm=config.llm_model,
        tts=config.tts_model,
    )
    
    # 3. Connect to room
    await ctx.connect()
    
    # 4. Start session
    await session.start(room=ctx.room)
    
    # 5. Set initial context
    session.chat_ctx.append(
        role="system",
        content="Your system prompt here"
    )
```

### 2. Active Conversation Phase

```
User speaks -> STT transcription -> LLM processing -> TTS generation -> Agent speaks
     ↑                                    |
     |                                    ↓
     └────────────────────────── Tool execution (optional)
```

### 3. Termination Phase

```python
# Graceful shutdown triggered by:
# - User disconnection
# - Room closure
# - Worker shutdown (SIGTERM)
# - Agent completion

# Session cleanup automatic:
# - STT/LLM/TTS streams closed
# - Database connections cleaned up
# - Resources released
```

---

## Building Custom Agents

### Basic Agent Structure

```python
from livekit.agents import Agent, AgentSession, JobContext
from config import VoicePipelineConfig

class CustomAgent(Agent):
    """Custom agent with specialized behavior"""
    
    def __init__(self):
        super().__init__(
            instructions="""You are a specialized assistant.
            Your specific role and personality here."""
        )
    
    async def on_enter(self) -> None:
        """Called when agent becomes active"""
        await self.session.generate_reply(
            instructions="Greet the user appropriately"
        )
    
    async def on_exit(self) -> None:
        """Called before agent hands off or exits"""
        # Cleanup, save state, etc.
        pass
```

### Using Custom Agents

```python
async def entrypoint(ctx: JobContext):
    config = VoicePipelineConfig()
    
    session = AgentSession(
        stt=config.stt_model,
        llm=config.llm_model,
        tts=config.tts_model,
        agent=CustomAgent()  # Use your custom agent
    )
    
    await ctx.connect()
    await session.start(room=ctx.room)
    await asyncio.sleep(float('inf'))
```

---

## Multi-Agent Workflows

### Agent Handoff Pattern

```python
class ReceptionAgent(Agent):
    """First contact agent - routes to specialists"""
    
    def __init__(self):
        super().__init__(
            instructions="""You are a reception agent. 
            Determine what the user needs and route them."""
        )
    
    @function_tool()
    async def transfer_to_billing(self, context: RunContext):
        """Transfer to billing specialist"""
        return BillingAgent(chat_ctx=self.chat_ctx), "Transferring to billing"
    
    @function_tool()
    async def transfer_to_support(self, context: RunContext):
        """Transfer to technical support"""
        return SupportAgent(chat_ctx=self.chat_ctx), "Transferring to support"


class BillingAgent(Agent):
    """Specialized billing agent"""
    
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="You are a billing specialist...",
            chat_ctx=chat_ctx  # Preserve conversation history
        )
    
    async def on_enter(self):
        await self.session.generate_reply(
            instructions="Introduce yourself as billing specialist"
        )
```

### Sequential Workflow Pattern

```python
class OnboardingWorkflow:
    """Multi-step onboarding process"""
    
    async def start(self, session: AgentSession):
        # Step 1: Collect user info
        user_info = await CollectInfoAgent(session).run()
        
        # Step 2: Verify information
        verified = await VerificationAgent(session, user_info).run()
        
        # Step 3: Complete setup
        if verified:
            await SetupAgent(session, user_info).run()
        
        # Step 4: Hand off to main agent
        session.update_agent(MainAgent(user_info=user_info))
```

### Parallel Agent Pattern

```python
class SupervisorAgent(Agent):
    """Coordinates multiple specialist agents"""
    
    @function_tool()
    async def research_topic(self, context: RunContext, topic: str):
        """Research using multiple sources"""
        
        # Query multiple specialized agents in parallel
        tasks = [
            WebSearchAgent().search(topic),
            DatabaseAgent().query(topic),
            KnowledgeBaseAgent().lookup(topic)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Synthesize results
        return self._synthesize(results)
```

---

## Tool Development

### Basic Tool Structure

```python
from livekit.agents import function_tool, RunContext
from typing import Annotated

@function_tool()
async def tool_name(
    context: RunContext,
    param1: Annotated[str, "Description of param1"],
    param2: Annotated[int, "Description of param2"] = 10
) -> str:
    """
    Clear description of what this tool does.
    The LLM uses this to decide when to call the tool.
    """
    
    # 1. Validate inputs
    if not param1:
        return "Error: param1 is required"
    
    # 2. Perform operation
    try:
        result = await some_async_operation(param1, param2)
    except Exception as e:
        logger.error(f"Tool error: {e}")
        return f"Error: {str(e)}"
    
    # 3. Return user-friendly result
    return f"Operation completed: {result}"
```

### Tool Best Practices

**1. Clear Descriptions:**
```python
@function_tool()
async def get_weather(
    context: RunContext,
    location: Annotated[str, "City name or zip code, e.g. 'San Francisco' or '94102'"]
) -> str:
    """
    Get current weather for a location.
    Use this when user asks about weather, temperature, or conditions.
    Examples: "What's the weather?", "Is it raining in Boston?"
    """
```

**2. Error Handling:**
```python
@function_tool()
async def query_database(context: RunContext, query: str) -> str:
    try:
        result = await db.query(query)
        if not result:
            return "No results found"
        return str(result)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        return "I encountered a database error. Please try again."
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return "An unexpected error occurred."
```

**3. User-Friendly Responses:**
```python
@function_tool()
async def check_inventory(context: RunContext, product_id: str) -> str:
    quantity = await inventory.check(product_id)
    
    # Don't just return raw data
    # ❌ return str(quantity)
    
    # Format for voice conversation
    # ✅
    if quantity == 0:
        return "This item is currently out of stock."
    elif quantity < 5:
        return f"We have {quantity} units left in stock. Limited availability."
    else:
        return f"This item is in stock with {quantity} units available."
```

### Database-Connected Tools

```python
from db_integration import DatabaseManager, get_cached_or_query

@function_tool()
async def lookup_customer(
    context: RunContext,
    customer_id: Annotated[str, "Customer ID or email address"]
) -> str:
    """Look up customer information by ID or email"""
    
    db_manager = DatabaseManager()
    
    # Use caching for frequently accessed data
    async def query():
        return await db_manager.db.query(
            """SELECT name, account_type, total_orders 
               FROM customers 
               WHERE id = $1 OR email = $1""",
            (customer_id,)
        )
    
    results = await get_cached_or_query(
        cache_key=f"customer:{customer_id}",
        query_func=query,
        expiry=300  # 5 minutes
    )
    
    if not results:
        return f"No customer found with ID {customer_id}"
    
    customer = results[0]
    return f"{customer['name']} - {customer['account_type']} account with {customer['total_orders']} orders"
```

### Multi-Step Tools

```python
@function_tool()
async def process_order(
    context: RunContext,
    product_id: str,
    quantity: int
) -> str:
    """Process a customer order"""
    
    # Step 1: Validate inventory
    available = await check_inventory_internal(product_id)
    if available < quantity:
        return f"Sorry, only {available} units available"
    
    # Step 2: Calculate price
    price = await get_price(product_id, quantity)
    
    # Step 3: Create order
    order_id = await create_order_internal(
        user_id=context.session.userdata.user_id,
        product_id=product_id,
        quantity=quantity,
        total=price
    )
    
    # Step 4: Reserve inventory
    await reserve_inventory(product_id, quantity, order_id)
    
    return f"Order {order_id} created for {quantity} units. Total: ${price:.2f}"
```

---

## State Management

### Session-Level State

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ConversationState:
    """Custom state for your conversation"""
    user_id: Optional[str] = None
    authenticated: bool = False
    shopping_cart: list = None
    preferences: dict = None
    
    def __post_init__(self):
        if self.shopping_cart is None:
            self.shopping_cart = []
        if self.preferences is None:
            self.preferences = {}

# Create session with custom state
session = AgentSession[ConversationState](
    stt=config.stt_model,
    llm=config.llm_model,
    tts=config.tts_model,
    userdata=ConversationState()
)

# Access state in tools
@function_tool()
async def add_to_cart(context: RunContext[ConversationState], product_id: str):
    context.userdata.shopping_cart.append(product_id)
    return f"Added to cart. You now have {len(context.userdata.shopping_cart)} items."
```

### Persistent State (Database)

```python
class StatefulAgent(Agent):
    """Agent that persists state to database"""
    
    async def on_enter(self):
        # Load previous conversation state
        state = await self._load_state(self.session.userdata.user_id)
        if state:
            self.session.userdata.update(state)
            await self.session.generate_reply(
                instructions=f"Welcome back! Last time we talked about {state.get('last_topic')}"
            )
    
    async def on_exit(self):
        # Save state before exiting
        await self._save_state(
            user_id=self.session.userdata.user_id,
            state=self.session.userdata
        )
    
    async def _load_state(self, user_id: str):
        db = DatabaseManager().db
        results = await db.query(
            "SELECT state FROM conversation_state WHERE user_id = $1",
            (user_id,)
        )
        return results[0]['state'] if results else None
    
    async def _save_state(self, user_id: str, state):
        db = DatabaseManager().db
        await db.execute(
            """INSERT INTO conversation_state (user_id, state, updated_at)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE SET state = $2, updated_at = $3""",
            (user_id, state, datetime.now())
        )
```

---

## Advanced Patterns

### Context-Aware Agents

```python
class ContextAwareAgent(Agent):
    """Agent that adapts based on conversation context"""
    
    async def before_llm_inference(self, chat_ctx):
        """Hook to modify context before LLM call"""
        
        # Analyze recent messages
        recent_topics = self._extract_topics(chat_ctx.messages[-5:])
        
        # Add context-specific instructions
        if "technical" in recent_topics:
            chat_ctx.append(
                role="system",
                content="User is discussing technical topics. Use precise terminology."
            )
        elif "frustrated" in self._detect_sentiment(chat_ctx):
            chat_ctx.append(
                role="system",
                content="User seems frustrated. Be extra patient and helpful."
            )
        
        return chat_ctx
```

### Dynamic Model Switching

```python
class AdaptiveAgent(Agent):
    """Switches models based on requirements"""
    
    @function_tool()
    async def handle_complex_query(self, context: RunContext, query: str):
        """Handle complex reasoning task"""
        
        # Switch to more capable model for complex task
        original_llm = context.session.llm
        context.session.update_llm("openai/gpt-4.1")  # Upgrade to better model
        
        try:
            result = await self.session.generate_reply(
                instructions=f"Analyze this complex query: {query}"
            )
        finally:
            # Switch back to faster model
            context.session.update_llm(original_llm)
        
        return result
```

### Interrupt Handling

```python
class InterruptibleAgent(Agent):
    """Agent that handles user interruptions gracefully"""
    
    def __init__(self):
        super().__init__(
            instructions="You can be interrupted. Stay polite.",
            turn_detection="multilingual"  # Enables interruption detection
        )
    
    async def on_user_speech_started(self):
        """Called when user starts speaking (potential interrupt)"""
        # Stop current TTS output
        await self.session.cancel_speech()
        logger.info("User interrupted - stopping speech")
    
    async def on_user_speech_committed(self, transcript: str):
        """Called when user speech is finalized"""
        # Process the interruption
        await self.session.generate_reply()
```

---

## Performance Optimization

### 1. Minimize Latency

```python
# ✅ Good: Stream responses immediately
await session.generate_reply()  # Starts speaking as soon as first chunk ready

# ❌ Bad: Wait for complete response
response = await session.generate_full_reply()
await session.say(response)
```

### 2. Optimize Tool Calls

```python
# ✅ Good: Parallel tool execution when possible
async def research_product(product_id: str):
    inventory, pricing, reviews = await asyncio.gather(
        check_inventory(product_id),
        get_pricing(product_id),
        get_reviews(product_id)
    )
    return combine_results(inventory, pricing, reviews)

# ❌ Bad: Sequential calls
async def research_product_slow(product_id: str):
    inventory = await check_inventory(product_id)
    pricing = await get_pricing(product_id)
    reviews = await get_reviews(product_id)
    return combine_results(inventory, pricing, reviews)
```

### 3. Cache Frequently Accessed Data

```python
from db_integration import get_cached_or_query

@function_tool()
async def get_product_info(context: RunContext, product_id: str):
    # Cache for 1 hour
    return await get_cached_or_query(
        cache_key=f"product:{product_id}",
        query_func=lambda: db.query("SELECT * FROM products WHERE id = $1", product_id),
        expiry=3600
    )
```

### 4. Optimize System Prompts

```python
# ✅ Good: Concise, focused prompts
instructions = """You are a helpful assistant. 
Be brief and conversational."""

# ❌ Bad: Overly long prompts
instructions = """You are an extremely helpful and detailed assistant 
who always provides comprehensive answers with multiple paragraphs 
explaining every possible angle..."""  # Increases latency!
```

---

## Testing Agents

### Unit Testing Tools

```python
import pytest
from agent import my_tool

@pytest.mark.asyncio
async def test_my_tool():
    # Create mock context
    class MockContext:
        userdata = {"user_id": "test123"}
    
    context = MockContext()
    
    # Test tool
    result = await my_tool(context, param1="test")
    
    assert "expected" in result
    assert result != "Error"
```

### Integration Testing

```python
async def test_full_conversation():
    """Test complete conversation flow"""
    
    # 1. Create test room
    room_name = await create_test_room()
    
    # 2. Generate token
    token, _ = generate_token("test-user", "Test User", room_name)
    
    # 3. Connect test client
    client = VoiceTestClient()
    await client.connect(token, os.getenv("LIVEKIT_URL"))
    
    # 4. Simulate conversation
    # (Requires audio input/output simulation)
    
    # 5. Verify agent responses
    # Check logs, database state, etc.
    
    await client.disconnect()
```

### Load Testing

```bash
# Use testing.py to create multiple concurrent connections
for i in {1..10}; do
    python testing.py test-connection --duration 60 &
done
wait
```

---

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Log Tool Calls

```python
@function_tool()
async def my_tool(context: RunContext, param: str):
    logger.info(f"Tool called with param: {param}")
    logger.debug(f"Full context: {context}")
    
    try:
        result = await operation(param)
        logger.info(f"Tool result: {result}")
        return result
    except Exception as e:
        logger.error(f"Tool error: {e}", exc_info=True)
        raise
```

### Monitor Session State

```python
async def entrypoint(ctx: JobContext):
    session = AgentSession(...)
    
    # Log all messages
    @session.on("message")
    def on_message(msg):
        logger.info(f"Message: {msg.role} - {msg.content}")
    
    await session.start(room=ctx.room)
```

---

## Best Practices Summary

1. **Keep prompts concise** - Reduces latency and token usage
2. **Use streaming** - Start speaking immediately, don't wait
3. **Cache aggressively** - Especially for product/reference data
4. **Handle errors gracefully** - Always return user-friendly messages
5. **Test with real users** - Voice AI behaves differently than chat
6. **Monitor latency** - Track P50, P95, P99 response times
7. **Use appropriate models** - Balance quality vs speed
8. **Implement graceful degradation** - Fallback when services fail
9. **Log everything** - You'll need it for debugging
10. **Iterate based on data** - Use analytics to improve prompts and flows

---

For more examples, see the `/examples` directory in the project.