from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import time

console = Console()

def simulate_agent_stream(prompt):
    """Simulate a streaming response from an agent"""
    response = f"""Based on your input "{prompt}", let me provide a detailed analysis.

First, I'll break down the key components of your request. This involves understanding 
the context, identifying the main objectives, and determining the best approach to 
address your needs effectively.

Now, let's dive deeper into the technical aspects. We need to consider multiple factors 
including performance optimization, code maintainability, and scalability. Each of these 
elements plays a crucial role in building robust solutions.

Furthermore, it's important to think about edge cases and error handling. A well-designed 
system anticipates potential issues and handles them gracefully, ensuring a smooth user 
experience even when things don't go as planned.

In conclusion, the approach I recommend involves iterative development with continuous 
testing and refinement. This methodology allows us to adapt quickly and deliver high-quality 
results that meet your specific requirements."""
    
    # Yield response word by word to simulate streaming
    words = response.split()
    for word in words:
        yield word + " "
        time.sleep(0.05)  # Simulate network delay

def run_interactive_session():
    conversation_history = []
    token_count = 0
    
    while True:
        # Get user input
        console.print("\n[bold cyan]You:[/bold cyan]", end=" ")
        user_input = input()
        
        if user_input.lower() in ['exit', 'quit']:
            console.print("[yellow]Goodbye![/yellow]")
            break
        
        conversation_history.append(f"[bold cyan]You:[/bold cyan] {user_input}")
        
        # Create layout
        layout = Layout()
        layout.split_column(
            Layout(name="main", ratio=5),
            Layout(name="status", ratio=1)
        )
        
        # Stream agent response
        agent_response = ""
        with Live(layout, refresh_per_second=10, screen=False) as live:
            console.print("\n[bold green]Agent:[/bold green] ", end="")
            
            for chunk in simulate_agent_stream(user_input):
                agent_response += chunk
                token_count += 1
                
                # Update main panel with conversation
                conversation_text = "\n\n".join(conversation_history)
                conversation_text += f"\n\n[bold green]Agent:[/bold green] {agent_response}"
                
                layout["main"].update(
                    Panel(
                        Text.from_markup(conversation_text),
                        title="💬 Conversation",
                        border_style="blue"
                    )
                )
                
                # Update status panel with token usage
                layout["status"].update(
                    Panel(
                        f"[bold]Tokens:[/bold] {token_count} | [bold]Response length:[/bold] {len(agent_response)} chars",
                        title="📊 Token Usage",
                        style="cyan"
                    )
                )
                
                live.update(layout)
            
            conversation_history.append(f"[bold green]Agent:[/bold green] {agent_response}")
            
            # Show final state for a moment
            time.sleep(1)

if __name__ == "__main__":
    console.print("[bold magenta]🤖 Interactive Agent Chat[/bold magenta]")
    console.print("[dim]Type 'exit' or 'quit' to end the session[/dim]\n")
    run_interactive_session()