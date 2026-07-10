"""
Jarvis Desktop Theme

Defines the complete visual identity of Jarvis OS Desktop.
All colours, typography, spacing and animation constants live here.
No widget should hardcode visual values.
"""


class Theme:
    """
    Central theme configuration for Jarvis OS Desktop.
    """

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    WINDOW_WIDTH = 1280
    WINDOW_HEIGHT = 820
    WINDOW_TITLE = "Jarvis OS"

    SIDEBAR_WIDTH = 220

    # ------------------------------------------------------------------
    # Colours
    # ------------------------------------------------------------------

    # Backgrounds
    BACKGROUND        = "#0D1117"
    SURFACE           = "#161B22"
    SURFACE_ELEVATED  = "#1C2330"
    SURFACE_HOVER     = "#21293A"

    # Accent
    ACCENT            = "#00A8FF"
    ACCENT_DIM        = "#0070CC"
    ACCENT_HOVER      = "#38BDF8"
    ACCENT_GLOW       = "rgba(0, 168, 255, 0.15)"
    ACCENT_RING       = "rgba(0, 168, 255, 0.35)"

    # Text
    TEXT              = "#E6EDF3"
    TEXT_SECONDARY    = "#7D8590"
    TEXT_MUTED        = "#484F58"

    # Borders
    BORDER            = "#21262D"
    BORDER_ACCENT     = "rgba(0, 168, 255, 0.25)"

    # Status
    SUCCESS           = "#3FB950"
    WARNING           = "#D29922"
    ERROR             = "#F85149"
    OFFLINE           = "#484F58"

    # Message bubbles
    BUBBLE_JARVIS     = "#161B22"
    BUBBLE_USER       = "#0D2137"
    BUBBLE_SYSTEM     = "#0D1117"

    # ------------------------------------------------------------------
    # Orb colours
    # ------------------------------------------------------------------

    ORB_IDLE          = "#00A8FF"
    ORB_LISTENING     = "#00D4FF"
    ORB_THINKING      = "#3B82F6"
    ORB_SPEAKING      = "#00FF88"
    ORB_ERROR         = "#F85149"
    ORB_OFFLINE       = "#484F58"

    # ------------------------------------------------------------------
    # Typography
    # ------------------------------------------------------------------

    FONT_FAMILY       = "Segoe UI"
    FONT_MONO         = "Consolas"

    FONT_XS           = 10
    FONT_SMALL        = 11
    FONT_NORMAL       = 13
    FONT_MEDIUM       = 14
    FONT_LARGE        = 16
    FONT_TITLE        = 22
    FONT_HERO         = 28

    # ------------------------------------------------------------------
    # Spacing
    # ------------------------------------------------------------------

    RADIUS_SM         = 6
    RADIUS_MD         = 10
    RADIUS_LG         = 16
    RADIUS_FULL       = 999

    MARGIN            = 16
    SPACING_SM        = 8
    SPACING_MD        = 14
    SPACING_LG        = 20

    INPUT_HEIGHT      = 46
    BUTTON_HEIGHT     = 46

    CHAT_PADDING      = 20
    BUBBLE_PADDING    = "12px 16px"

    HEADER_HEIGHT     = 52

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    ANIM_FAST         = 150    # ms
    ANIM_NORMAL       = 300    # ms
    ANIM_SLOW         = 600    # ms

    ORB_PULSE_SPEED   = 2000   # ms per cycle
    ORB_SIZE          = 120    # px diameter