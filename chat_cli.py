import sys
import os
import asyncio
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_ORANGE = "\033[38;5;208m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"


def print_banner():
    print(f"{COLOR_ORANGE}{COLOR_BOLD}")
    print("=" * 60)
    print("  🔥 Portgas D. Ace AI Desktop Companion - Terminal CLI 🔥")
    print("=" * 60)
    print(f"{COLOR_RESET}{COLOR_DIM}")
    print("Commands: /help, /tools, /memory, /clear, /speak [on|off], /exit")
    print(f"Model: {settings.OLLAMA_MODEL} | Base URL: {settings.OLLAMA_URL}")
    print("-" * 60 + COLOR_RESET)


async def run_cli(session_id: str = "cli", default_speak: bool = False):
    from backend.agent.chat_service import chat_service
    from backend.memory.conversation import clear_conversation, get_long_term_memories
    from backend.agent.tools import TOOL_MAP

    print_banner()
    speak = default_speak
    print(f"{COLOR_DIM}[Voice Speech TTS: {'ON' if speak else 'OFF'} (toggle with /speak)]{COLOR_RESET}\n")

    while True:
        try:
            prompt_header = f"{COLOR_CYAN}{COLOR_BOLD}You > {COLOR_RESET}"
            user_input = input(prompt_header).strip()
            if not user_input:
                continue

            # Check slash commands
            cmd = user_input.lower()
            if cmd in ["/exit", "/quit", "exit", "quit"]:
                print(f"{COLOR_ORANGE}Ace: See you on the seas! 🔥{COLOR_RESET}")
                break

            if cmd == "/help":
                print(f"\n{COLOR_BOLD}📌 CLI Slash Commands:{COLOR_RESET}")
                print(f"  {COLOR_CYAN}/help{COLOR_RESET}           - Show this help menu")
                print(f"  {COLOR_CYAN}/tools{COLOR_RESET}          - List desktop tools available to the agent")
                print(f"  {COLOR_CYAN}/memory{COLOR_RESET}         - Inspect long-term memories")
                print(f"  {COLOR_CYAN}/clear{COLOR_RESET}          - Reset current chat session history")
                print(f"  {COLOR_CYAN}/speak on|off{COLOR_RESET}  - Enable/disable speech audio playback")
                print(f"  {COLOR_CYAN}/exit{COLOR_RESET}           - Exit CLI\n")
                continue

            if cmd == "/tools":
                print(f"\n{COLOR_YELLOW}{COLOR_BOLD}🛠️ Available Agent Tools:{COLOR_RESET}")
                for name, info in TOOL_MAP.items():
                    desc = info.get("description", "No description")
                    print(f"  • {COLOR_BOLD}{name}{COLOR_RESET}: {desc}")
                print()
                continue

            if cmd == "/memory":
                memories = get_long_term_memories()
                print(f"\n{COLOR_GREEN}{COLOR_BOLD}🧠 Long-Term Memories ({len(memories)} entries):{COLOR_RESET}")
                if memories:
                    for m in memories:
                        print(f"  • {m}")
                else:
                    print("  (No stored long-term memories yet)")
                print()
                continue

            if cmd == "/clear":
                clear_conversation(session_id=session_id)
                print(f"{COLOR_DIM}Active conversation history cleared.{COLOR_RESET}\n")
                continue

            if cmd.startswith("/speak"):
                parts = cmd.split()
                if len(parts) > 1 and parts[1] in ["on", "1", "true"]:
                    speak = True
                elif len(parts) > 1 and parts[1] in ["off", "0", "false"]:
                    speak = False
                else:
                    speak = not speak
                print(f"{COLOR_DIM}Voice speech TTS is now: {'ON' if speak else 'OFF'}{COLOR_RESET}\n")
                continue

            # Stream Chat Generation
            print(f"\n{COLOR_ORANGE}{COLOR_BOLD}🔥 Ace > {COLOR_RESET}", end="", flush=True)

            async for event in chat_service.stream_chat(
                message=user_input,
                session_id=session_id,
                speak=speak
            ):
                ev_type = event.get("type")
                if ev_type == "tool_start":
                    tool_desc = event.get("tool", "")
                    print(f"\n{COLOR_YELLOW}[⚡ Tool: {tool_desc}]{COLOR_RESET}\n{COLOR_ORANGE}{COLOR_BOLD}🔥 Ace > {COLOR_RESET}", end="", flush=True)
                elif ev_type == "token":
                    token = event.get("content", "")
                    sys.stdout.write(token)
                    sys.stdout.flush()
                elif ev_type == "done" and event.get("cached"):
                    src = event.get("source", "cache")
                    print(f"\n{COLOR_GREEN}{COLOR_DIM}[⚡ Instant Cache Hit: {src}]{COLOR_RESET}", end="", flush=True)
                elif ev_type == "error":
                    print(f"\n{COLOR_RED}[Error: {event.get('error')}]{COLOR_RESET}")

            print("\n")

        except KeyboardInterrupt:
            print(f"\n{COLOR_DIM}[Interrupted]{COLOR_RESET}")
        except EOFError:
            break
        except Exception as e:
            print(f"\n{COLOR_RED}Error: {e}{COLOR_RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Portgas D. Ace AI Desktop Agent - Terminal Chat CLI")
    parser.add_argument("--speak", action="store_true", default=False, help="Enable TTS speech playback")
    parser.add_argument("--session", type=str, default="cli", help="Session ID for conversation history")
    args = parser.parse_args()

    # Enable Windows ANSI escape sequence processing
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    asyncio.run(run_cli(session_id=args.session, default_speak=args.speak))


if __name__ == "__main__":
    main()
