"""Heritage Woodworks & Joinery — WhatsApp Web AI Master Carpenter Assistant.

Streamlit frontend with authentic WhatsApp Web aesthetics:
- WhatsApp Web message bubbles (#D9FDD3 outgoing, #FFFFFF incoming, tails, timestamps).
- Multi-step observable reasoning trace via collapsible expanders under each reply.
- Pinned bottom chat input with interactive quick-action buttons.
- Fully autonomous backend tool calling with calculate_material_needs, check_inventory_stock,
  and get_joinery_specs.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any, Dict, List

import streamlit as st

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent import carpenter_agent

# -----------------------------------------------------------------------------
# 1. Page Configuration & Custom WhatsApp Web Theme CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Heritage Woodworks — WhatsApp Assistant",
    page_icon="🪵",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Custom CSS injected for WhatsApp Web styling
WHATSAPP_CSS = """
<style>
/* Reset and background */
.stApp {
    background-color: #EFEAE2 !important;
    background-image: radial-gradient(#d3cbbe 1px, transparent 1px);
    background-size: 20px 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* Header styling */
.wa-header {
    background: linear-gradient(135deg, #075E54 0%, #008069 100%);
    color: #FFFFFF;
    padding: 14px 20px;
    border-radius: 12px 12px 0 0;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    margin-bottom: 15px;
}

.wa-avatar {
    width: 48px;
    height: 48px;
    background-color: #25D366;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    border: 2px solid #FFFFFF;
}

.wa-header-info h3 {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
    color: #FFFFFF;
}

.wa-header-info p {
    margin: 2px 0 0 0;
    font-size: 12px;
    color: #E0F2F1;
    display: flex;
    align-items: center;
    gap: 6px;
}

.wa-online-dot {
    width: 8px;
    height: 8px;
    background-color: #25D366;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 4px #25D366;
}

/* Chat container and bubbles */
.wa-chat-container {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px 0 30px 0;
}

/* User Message Bubble (Outgoing) */
.wa-msg-user-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 6px;
}

.wa-msg-user {
    background-color: #D9FDD3;
    color: #111B21;
    padding: 9px 14px 7px 14px;
    border-radius: 8px 8px 0px 8px;
    max-width: 82%;
    box-shadow: 0 1px 2px rgba(11,20,26,0.13);
    position: relative;
    font-size: 14.5px;
    line-height: 1.45;
    word-break: break-word;
}

.wa-msg-user::after {
    content: "";
    position: absolute;
    bottom: 0;
    right: -8px;
    width: 0;
    height: 0;
    border-top: 9px solid transparent;
    border-left: 9px solid #D9FDD3;
}

/* Assistant Message Bubble (Incoming) */
.wa-msg-bot-wrapper {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 6px;
}

.wa-msg-bot {
    background-color: #FFFFFF;
    color: #111B21;
    padding: 10px 15px 8px 15px;
    border-radius: 8px 8px 8px 0px;
    max-width: 85%;
    box-shadow: 0 1px 2px rgba(11,20,26,0.13);
    position: relative;
    font-size: 14.5px;
    line-height: 1.5;
    word-break: break-word;
}

.wa-msg-bot::after {
    content: "";
    position: absolute;
    bottom: 0;
    left: -8px;
    width: 0;
    height: 0;
    border-top: 9px solid transparent;
    border-right: 9px solid #FFFFFF;
}

/* Timestamp in bubbles */
.wa-time {
    font-size: 11px;
    color: #667781;
    text-align: right;
    margin-top: 4px;
    user-select: none;
}

/* Status badge for tools in sidebar */
.tool-pill {
    background: #E8F5E9;
    color: #1B5E20;
    padding: 4px 9px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
    display: inline-block;
    margin: 2px 0;
    border: 1px solid #C8E6C9;
}

/* Expander styling */
div[data-testid="stExpander"] {
    background-color: #F8F9FA !important;
    border: 1px solid #DFE5E7 !important;
    border-radius: 8px !important;
    margin-top: 4px !important;
    margin-bottom: 12px !important;
}

div[data-testid="stExpander"] summary {
    color: #075E54 !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
}

/* Markdown formatting inside bubbles */
.wa-msg-bot p {
    margin-bottom: 6px;
}
.wa-msg-bot ul, .wa-msg-bot ol {
    padding-left: 20px;
    margin-top: 4px;
    margin-bottom: 6px;
}

/* Hide Streamlit footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(WHATSAPP_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. Session State Initialization
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Namaste! 🙏 I am **Rajesh Sharma (Ustad Ji)**, Master Craftsman at **Heritage Woodworks & Joinery**.\n\n"
                "I am equipped with autonomous woodworking calculation and inventory tools. "
                "Ask me to estimate lumber, check timber stock, or recommend joinery & fasteners for your custom piece!"
            ),
            "timestamp": datetime.datetime.now().strftime("%I:%M %p"),
            "trace": [],
        }
    ]

# -----------------------------------------------------------------------------
# 3. Sidebar: Master Carpenter Profile & Tool Directory
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=500&auto=format&fit=crop&q=60",
        caption="Heritage Woodworks & Joinery Workshop",
        use_container_width=True,
    )
    st.markdown("### 🪵 Heritage Woodworks")
    st.caption("Custom Furniture & Joinery Specialists • Established 1998")

    st.markdown("---")
    st.markdown("#### 🛠️ Autonomous Woodworking Tools")
    st.markdown(
        """
        - <span class="tool-pill">📐 calculate_material_needs</span><br/>
          <small style='color:#555;'>Computes board feet, sq.ft, 15% cutting waste & ₹ costs.</small>
        - <span class="tool-pill">📦 check_inventory_stock</span><br/>
          <small style='color:#555;'>Verifies local yard stock, bay location & availability.</small>
        - <span class="tool-pill">🪚 get_joinery_specs</span><br/>
          <small style='color:#555;'>Hardware gauges, screw sizes, glue specs & curing.</small>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("#### ⚙️ Agent Engine Configuration")
    user_api_key = st.text_input(
        "Google Gemini API Key (Optional)",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="Optional: If left blank or default, the autonomous agent runs 100% locally with its built-in ReAct reasoning engine.",
    )

    if user_api_key and user_api_key != "your_gemini_api_key":
        st.success("🟢 Mode: Gemini LLM Function Calling Active")
    else:
        st.info("⚡ Mode: 100% Local Autonomous ReAct Engine (No API key needed)")

    st.markdown("---")
    st.markdown("#### 💡 Quick Test Tasks")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🪑 6x3 Teak Table", use_container_width=True):
            st.session_state.pending_prompt = "Estimate material for a 6x3 ft dining table in teak wood and verify stock"
        if st.button("🪚 Dovetail Specs", use_container_width=True):
            st.session_state.pending_prompt = "What are the specs, slope ratio, and glue for dovetail joints on drawers?"
    with col2:
        if st.button("🚪 7x4 Wardrobe", use_container_width=True):
            st.session_state.pending_prompt = "Estimate 7x4 ft wardrobe in marine ply and check stock for hinges"
        if st.button("📦 Check Stock", use_container_width=True):
            st.session_state.pending_prompt = "Check inventory stock for marine ply, Hettich hinges, and Fevicol Marine"

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Namaste! Chat history cleared. How may I assist you with your woodworking project today?",
                "timestamp": datetime.datetime.now().strftime("%I:%M %p"),
                "trace": [],
            }
        ]
        st.rerun()

# -----------------------------------------------------------------------------
# 4. Main WhatsApp Header
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="wa-header">
        <div class="wa-avatar">🪚</div>
        <div class="wa-header-info">
            <h3>Rajesh Sharma (Master Carpenter)</h3>
            <p><span class="wa-online-dot"></span> Online | Autonomous Woodworking Agent</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 5. Render Message History (with WhatsApp Bubbles and Observable Tool Traces)
# -----------------------------------------------------------------------------
for msg in st.session_state.messages:
    role = msg.get("role")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")
    trace = msg.get("trace", [])

    if role == "user":
        # Outgoing User Bubble
        st.markdown(
            f"""
            <div class="wa-msg-user-wrapper">
                <div class="wa-msg-user">
                    {content}
                    <div class="wa-time">{timestamp} ✓✓</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Incoming Assistant Bubble
        # Format text to convert line breaks to HTML friendly paragraphs
        formatted_content = content.replace("\n", "<br/>")
        st.markdown(
            f"""
            <div class="wa-msg-bot-wrapper">
                <div class="wa-msg-bot">
                    {formatted_content}
                    <div class="wa-time">{timestamp}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Observable Reasoning Trace (Collapsible Accordion / Expander)
        if trace:
            with st.expander(f"🔍 Agent Reasoning & Tool Trace ({len(trace)} Autonomous Steps)", expanded=False):
                for step_data in trace:
                    step_num = step_data.get("step", 1)
                    thought = step_data.get("thought", "")
                    tool_name = step_data.get("tool_name", "")
                    tool_args = step_data.get("tool_args", {})
                    observation = step_data.get("observation", {})

                    st.markdown(f"#### ⚙️ Step {step_num}: `{tool_name}`")
                    st.markdown(f"**🧠 Agent Reasoning:**\n> *{thought}*")

                    st.markdown(f"**🛠️ Tool Called & Parameters:**")
                    st.code(f"{tool_name}({', '.join(f'{k}={repr(v)}' for k, v in tool_args.items())})", language="python")

                    st.markdown("**📋 Observation Output:**")
                    if isinstance(observation, dict):
                        st.json(observation)
                    else:
                        st.markdown(f"```text\n{observation}\n```")
                    st.markdown("---")

# -----------------------------------------------------------------------------
# 6. Sticky Chat Input at Bottom & Task Execution
# -----------------------------------------------------------------------------
# Handle prompt from quick-action button if clicked
prompt = None
if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
else:
    prompt = st.chat_input("Message Rajesh Sharma (e.g. Estimate 6x3 ft dining table in teak wood and verify stock)...")

if prompt:
    now_str = datetime.datetime.now().strftime("%I:%M %p")

    # Append User Message to State
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "timestamp": now_str,
        "trace": [],
    })

    # Show live spinner while autonomous agent reasons and executes tools
    with st.spinner("🪵 Ustad Ji is analyzing dimensions, computing board feet, and checking timber stock..."):
        # Execute the autonomous tool loop
        result = carpenter_agent.run_agent_loop(
            user_message=prompt,
            chat_history=st.session_state.messages,
            custom_api_key=user_api_key,
        )

    # Append Assistant Response to State
    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("final_response", "Quotation prepared."),
        "timestamp": datetime.datetime.now().strftime("%I:%M %p"),
        "trace": result.get("trace", []),
    })

    # Immediate rerun to update WhatsApp speech bubbles
    st.rerun()
