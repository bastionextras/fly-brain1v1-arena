"""
================================================================================
 FLY BRAIN: BOSS FIGHT
 A 1v1 boss fight controlled by a simulated fly connectome (FlyWire FAFB).
================================================================================

FOLDER LAYOUT (place this file alongside these three, at your project root):

    flyproject/
    |-- main.py                        <- this file
    |-- connections_filtered.csv.gz    <- your FlyWire "Connections (Filtered)" export
    |-- opponent.png                   <- boss texture/sprite
    |-- death_sound.mp3                <- played when the fly dies

pandas reads a .csv.gz directly -- no need to unzip it yourself. If a
filename in your project doesn't match exactly, edit the CSV_PATH /
IMAGE_PATH / SOUND_PATH constants just below the installer block.

Run with:  python main.py   (from inside the flyproject folder, in VS Code's
integrated terminal, using whatever interpreter VS Code has selected -- the
installer block below installs into that exact interpreter automatically).
================================================================================
"""

# ==============================================================================
# AUTO-INSTALLER -- runs before anything else imports. Fixes "broken venv /
# wrong interpreter" problems by installing straight into sys.executable,
# i.e. whichever Python VS Code is actually running this file with.
# ==============================================================================
import importlib.util
import os
import shutil
import subprocess
import sys

REQUIRED_PACKAGES = {
    # import name -> pip package name
    "numpy": "numpy",
    "pandas": "pandas",
    "torch": "torch",
    "pygame": "pygame",
    "networkx": "networkx",
}


class _PipResult:
    def __init__(self, returncode, output):
        self.returncode = returncode
        self.output = output


def _run_pip_install(missing, extra_args=()):
    """Runs pip install, streaming its output live (torch alone can be a
    200+ MB download -- staying silent for a minute or two would look like
    a hang) while also collecting it so we can inspect *why* a failure
    happened and decide whether to retry differently."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "pip", "install", "--upgrade", *extra_args, *missing],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    lines = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    proc.wait()
    return _PipResult(proc.returncode, "".join(lines))


def _try_relaunch_under_uv_python(version="3.12"):
    """Installs `version` via uv (if not already present), finds its
    interpreter, and re-runs THIS SAME SCRIPT under it, inheriting the
    console so it's transparent to whoever launched it. On success this
    never returns -- it exits the process with the child run's exit code,
    since that child run is now the "real" one. Returns False only if the
    relaunch itself could not be set up (uv missing, install failed,
    interpreter not found), in which case the caller should fall back to
    printing manual instructions."""
    uv_path = shutil.which("uv")
    if not uv_path:
        print("[setup] 'uv' was not found on PATH, so this can't be fixed "
              "automatically. Manual steps below.")
        return False

    print(f"[setup] Found uv at {uv_path}. Installing Python {version} "
          "(it publishes wheels for everything this game needs) ...")
    try:
        subprocess.run(["uv", "python", "install", version], check=True)
        found = subprocess.run(
            ["uv", "python", "find", version],
            check=True, capture_output=True, text=True,
        )
        target_python = found.stdout.strip()
        if not target_python or not os.path.exists(target_python):
            print(f"[setup] 'uv python find {version}' didn't return a usable path "
                  f"(got: {target_python!r}).")
            return False
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[setup] Could not prepare Python {version} via uv ({exc}).")
        return False

    print(f"[setup] Relaunching this script under {target_python} ...")
    env = dict(os.environ)
    env["FLYBRAIN_RELAUNCH_ATTEMPTED"] = "1"  # guard against relaunch loops
    result = subprocess.run([target_python, os.path.abspath(__file__), *sys.argv[1:]], env=env)
    sys.exit(result.returncode)


def _ensure_packages():
    missing = [pip_name for import_name, pip_name in REQUIRED_PACKAGES.items()
               if importlib.util.find_spec(import_name) is None]
    if not missing:
        return

    print(f"[setup] Installing into {sys.executable}: {missing}")
    result = _run_pip_install(missing)

    if result.returncode != 0 and "externally-managed-environment" in result.output:
        # Common with uv-installed / distro-managed Pythons, which mark
        # themselves PEP 668 "externally managed" to steer people toward a
        # venv. For a standalone project script like this one, overriding
        # that guard is the standard, low-risk fix -- it's exactly what
        # pip's own error message suggests.
        print("[setup] This Python is marked 'externally managed' (common with "
              "uv-installed Pythons). Retrying with --break-system-packages...")
        result = _run_pip_install(missing, extra_args=["--break-system-packages"])

    if result.returncode != 0:
        print("[setup] pip install failed (see output above).")

        # Signs that pip couldn't find a prebuilt wheel for THIS Python
        # version/platform and fell back to compiling from source (which
        # then needs a C/C++ toolchain it usually doesn't have -- e.g.
        # 'distutils.msvccompiler' was removed from the stdlib in Python
        # 3.12+, which breaks older native-extension build scripts like
        # pygame's on brand-new Python versions). No pip flag or venv fixes
        # this -- the fix is a Python version these packages actually
        # publish wheels for.
        no_wheel_markers = (
            "No matching distribution found for",
            "Could not find a version that satisfies the requirement",
            "Failed to build",
            "distutils.msvccompiler",
            "msvccompiler",
            "Microsoft Visual C++",
        )
        looks_like_no_wheel = any(marker in result.output for marker in no_wheel_markers)

        if looks_like_no_wheel:
            print(f"[setup] This looks like one of {missing} has no prebuilt wheel "
                  f"for this exact Python build ({sys.version.split()[0]}) yet, and "
                  "the fallback source build failed (it needs Microsoft's C++ build "
                  "tools, which most machines don't have installed). No pip flag or "
                  "venv fixes this -- it needs a Python version these packages "
                  "already publish wheels for.")

            if os.environ.get("FLYBRAIN_RELAUNCH_ATTEMPTED") != "1":
                # Try to fix this automatically rather than just printing
                # instructions: install a known-good Python via uv (which is
                # already on this machine -- that's how the broken 3.14
                # interpreter got here) and re-run this exact script under
                # it. On success, _try_relaunch_under_uv_python exits the
                # process itself; we only reach the code below if that
                # setup failed.
                _try_relaunch_under_uv_python("3.12")
                print("[setup] Automatic relaunch under Python 3.12 didn't work; "
                      "falling back to manual instructions.")
            else:
                print("[setup] (Already tried relaunching once under a different "
                      "Python for this run -- not retrying again to avoid a loop.)")

            print("    Manual fix: uv python install 3.12, then in VS Code "
                  "Ctrl+Shift+P -> 'Python: Select Interpreter' -> pick the 3.12 one "
                  "-> re-run this file.")

        print("[setup] Or install manually in your VS Code terminal:")
        print(f"    {sys.executable} -m pip install --break-system-packages {' '.join(missing)}")
        print("[setup] Or, more cleanly, use a dedicated virtual environment instead:")
        print(f"    {sys.executable} -m venv .venv")
        print(r"    .venv\Scripts\activate      (Windows)   or   source .venv/bin/activate   (macOS/Linux)")
        print(f"    python -m pip install {' '.join(missing)}")
        sys.exit(1)

    print("[setup] Packages installed. If VS Code still can't see them, "
          "reload the window / re-select the interpreter (Ctrl+Shift+P -> "
          "'Python: Select Interpreter').")


_ensure_packages()

import os
import math
import random
import threading
import time
from collections import deque

import numpy as np
import pandas as pd
import torch
import torch.optim as optim
import pygame

# networkx is installed per your request, but is intentionally NOT run over
# the full connectome: building an nx.DiGraph across ~700k edges in pure
# Python would be slow and would defeat the entire point of using a sparse
# tensor for the real computation. It's used only by describe_sample_graph()
# below, an optional debug helper over a small random sample. Everything the
# game actually runs on uses the PyTorch sparse tensor.
import networkx as nx


# ==============================================================================
# CONFIG
# ==============================================================================
CSV_PATH = "connections_filtered.csv.gz"
IMAGE_PATH = "opponent.png"
SOUND_PATH = "death_sound.mp3"

SIDEBAR_W = 300   # left panel reserved for live brain/Watcher/learning stats
SCREEN_W, SCREEN_H = 1320, 960
ARENA_X = SIDEBAR_W  # the fight itself is drawn to the right of the sidebar
FPS = 60

NUM_HOPS = 6          # how many message-passing steps per brain decision
POOL_SIZE = 200        # neurons considered per role (sensory / motor), split 4 ways
DECISION_INTERVAL = 1.3   # seconds between brain decisions -- deliberately slow
# (was 0.35s) so a human can actually read which ability was chosen before it
# changes again. Fly.LABEL_DISPLAY_TIME below is derived from this so the
# on-screen ability label always stays up for (most of) the gap between
# decisions instead of flickering.
DECISION_TEMPERATURE = 0.12
# The connectome itself is an UNTRAINED, randomly-wired reservoir -- it is
# never trained, and apply_pain/apply_harmony perturbing its raw weights is
# noise injection, not learning (see the FlyBrain docstring). That means for
# any *fixed* sensory state its output is a deterministic function of that
# state, and while shuffling+calibrating the motor pools (see FlyBrain.
# _select_io_pools) fixed the *global* "always picks Dodge no matter the
# input" bias, the network can still get stuck confidently picking the same
# ability for long stretches whenever the boss/fly HP fractions stop
# changing. Sampling from a softmax over the logits instead of a hard argmax
# keeps the network's preference (the dominant ability is still picked most
# of the time) while adding enough variety that a stalled state doesn't last
# forever, and it's what lets fights actually reach a death or a win so the
# Watcher -- and now the trainable readout (see FlyBrain.learn_from_life) --
# have something to score and learn from.

LEARNING_RATE = 0.02   # Adam step size for the trainable readout (36 params)
WIN_REWARD = 1.2       # reward fed to learn_from_life() on a win -- above the
                       # ~0-1 range a death's Watcher score can reach, so the
                       # readout always treats winning as unambiguously best

LABEL_DISPLAY_TIME = min(DECISION_INTERVAL * 0.85, 2.0)  # how long the fly's
# ability-name label stays fully visible -- tied to DECISION_INTERVAL so it
# spans (most of) the gap until the next decision instead of flickering

FLY_MAX_HP = 30

# ==============================================================================
# BOSS DIFFICULTY -- every number that controls how tough the boss is lives
# here. Raise the damage/frequency numbers or lower the timing numbers to
# make it hit harder and more often; do the opposite to go easier.
# ==============================================================================
BOSS_MAX_HP = 200

# -- damage --------------------------------------------------------------
BOSS_ATTACK_MIN, BOSS_ATTACK_MAX = 10, 18   # damage dealt to the fly per landed
                                             # attack (was 6-12 -- a fly at
                                             # FLY_MAX_HP=30 could barely ever
                                             # die to that even when it *did*
                                             # get hit)
BOSS_DEFEND_DAMAGE_REDUCTION = 0.3   # multiplier on damage the FLY deals while
                                      # the boss is defending (lower = boss
                                      # blocks better)
BOSS_PUNISH_MULTIPLIER = 1.5         # bonus multiplier on the boss's NEXT
                                      # attack after the fly lands a Heavy
                                      # Attack -- the "risk/reward" mechanic
                                      # (see incoming_damage_timer in main())

# -- pacing (how often it attacks) ----------------------------------------
BOSS_IDLE_TIME_RANGE = (1.2, 2.2)    # how long it waits before choosing to
                                      # attack or defend
BOSS_TELEGRAPH_TIME = 0.9            # warning window before an attack lands
                                      # (red outline, "WINDING UP...") -- kept
                                      # long enough to actually read, and to
                                      # give a real window for a Parry
BOSS_ATTACK_TIME = 0.55              # how long the attack is "live" (orange
                                      # outline; deals its one hit during this
                                      # window)
BOSS_DEFEND_TIME = 1.8               # how long it defends before going idle
BOSS_DEFEND_CHANCE = 0.5             # probability it chooses to defend instead
                                      # of attack, each time it leaves idle
BOSS_HIT_FLASH_DURATION = 0.45       # how long the white "just got hit" flash
                                      # lingers -- slowed so it's actually
                                      # readable instead of a single-frame blip

# -- enrage: the boss gets meaner as it loses health, like a real boss fight --
BOSS_ENRAGE_HP_FRAC = 0.35           # below this HP fraction, enrage kicks in
BOSS_ENRAGE_DAMAGE_MULT = 1.4        # multiplies its attack damage while enraged
BOSS_ENRAGE_SPEED_MULT = 0.6         # multiplies idle/telegraph durations while
                                      # enraged (below 1.0 = attacks come faster)

ABILITY_NAMES = ["Light Attack", "Heavy Attack", "Parry", "Heal"]
ABILITY_COLORS = [(240, 200, 80), (230, 90, 70), (90, 190, 230), (110, 230, 150)]

# ==============================================================================
# PARRY MECHANIC -- what used to be a free, no-downside "Dodge" is now a
# proper risk/reward parry: timing it against the boss's TELEGRAPH (the
# warning window, before the hit lands) is a full punish -- no damage taken,
# a big counter hit, and the boss is staggered back to idle. Holding it only
# once the boss is already mid-ATTACK still works like the old Dodge (damage
# avoided, no bonus). Using it with no threat at all (boss idle/defending) is
# now a genuine mistake -- it's a whiff that costs the fly a little HP -- so
# spamming it as a safe default is no longer free. This is the main lever
# for "the fly needs more challenge": it raises the skill ceiling instead of
# just raising numbers.
# ==============================================================================
PARRY_COUNTER_DAMAGE_MIN, PARRY_COUNTER_DAMAGE_MAX = 15, 25  # bonus dmg to the
                                                              # boss on a perfect parry
PARRY_STAGGER_TIME = 1.8       # boss is forced back to idle for this long after
                                # being perfectly parried -- the reward window
PARRY_WHIFF_DAMAGE_MIN, PARRY_WHIFF_DAMAGE_MAX = 3, 6  # self-damage for parrying
                                                        # with nothing to parry

# -- Watcher (Critic) tuning --------------------------------------------------
BASE_PAIN_INTENSITY = 25.0        # pain applied at pain_scale == 1.0 (maximum)
MIN_PAIN_SCALE = 0.15             # pain never drops to exactly zero -- some
                                   # learning signal always survives a death
REFERENCE_SURVIVAL_SECONDS = 12.0  # "good" survival time, for normalizing the score
REFERENCE_DODGE_COUNT = 4          # "good" number of successful (reactive) dodges
REFERENCE_PARRY_COUNT = 2          # "good" number of PERFECT parries in one life --
                                    # lower than dodges since they're harder to land
STILL_DEATH_TIME = 1.0            # below this...
STILL_DEATH_DAMAGE = 2.0          # ...and this little damage dealt...
#                                    ...with zero dodges/parries = "stood still and
#                                    died instantly" -> maximum pain regardless of history
LOGIT_HISTORY_LEN = 150           # how many past decisions the sidebar chart shows
SCORE_HISTORY_LEN = 40            # how many past lives the Watcher sparkline shows


# ==============================================================================
# PART 1: THE PYTORCH BRAIN ENGINE
# ==============================================================================
class FlyBrain:
    """
    A decision engine built directly from a FlyWire FAFB connectome
    'Connections (Filtered)' CSV export.

    Design notes (validated empirically while building this against the
    real dataset -- 138,584 neurons, 5.34M connection rows collapsing to
    3.73M unique directed edges after coalescing -- not guessed):

    - The adjacency matrix is a torch sparse tensor. At this scale, a dense
      NxN matrix would need ~150GB of RAM (138,584^2 floats); sparse keeps
      the whole thing under ~2GB.

    - The filtered connections CSV alone has no "this is a photoreceptor" /
      "this is a motor neuron" column -- that lives in FlyWire's separate
      cell-type annotation tables, which weren't provided. As a stand-in,
      roles are assigned structurally: neurons whose out-degree heavily
      exceeds their in-degree become sensory-input targets (they mostly
      broadcast outward); neurons whose in-degree heavily exceeds their
      out-degree become motor-output readouts (they mostly collect
      signal). This is a heuristic proxy, not real cell typing -- calling
      that out plainly rather than dressing it up.

    - A single hop of propagation (state @ adjacency) essentially never
      reaches the motor pool in a graph this large and sparse -- confirmed
      directly before writing this class. Decisions propagate the signal
      for several hops, accumulating activation across all of them, and
      read a *pooled group* of ~50 motor neurons per ability rather than
      one specific neuron each. That pooling matters: reading a single
      neuron per ability is fragile and frequently returns all-zero output
      no matter what the boss is doing.

    - torch.sparse_coo_tensor is what you build the graph FROM (indices +
      values), but it is a poor choice for the repeated matmul a decision
      needs: at this dataset's real scale one 6-hop decision measured
      ~0.9s in COO format -- clearly too slow to run several times a
      second. Converting the (fixed) index structure to CSR format once
      and reusing it dropped that to ~30-40ms, a ~25x speedup, with
      identical numerical results. So COO indices/values are kept as the
      mutable "source of truth" (pain/harmony change the values), and a
      CSR snapshot built from them is what decide() actually reads.

    - Rebuilding that CSR snapshot after a pain/harmony weight change still
      takes over a second at this scale (coalescing + reformatting ~3.7M
      edges). Doing that synchronously inside the game loop would freeze
      the whole window -- not just the intended "THE FLY DIED" overlay,
      but the OS event pump too, which can make it look hung. So
      apply_pain() / apply_harmony() dispatch the rebuild onto its own
      background thread and return immediately; decide() just keeps using
      the last-ready CSR snapshot until the new one swaps in (reading and
      replacing a Python attribute is atomic under the GIL, so no lock is
      needed for that handoff -- confirmed safe under concurrent access).
    """

    def __init__(self, csv_path, device="cpu", num_hops=NUM_HOPS, pool_size=POOL_SIZE):
        self.device = device
        self.num_hops = num_hops
        self.locked = False  # True after a win: weights stop reacting to pain
        self._mutate_lock = threading.Lock()  # serializes value mutations (pain/harmony)
        self._pending_rebuilds = []  # background rebuild threads, joined on shutdown

        df = pd.read_csv(csv_path)
        pre_col, post_col, weight_col, nt_col = self._detect_columns(df)

        print(f"[brain] Loaded {len(df):,} rows from {csv_path}")
        print(f"[brain] Using columns: pre={pre_col}, post={post_col}, "
              f"weight={weight_col or '(none found, defaulting to 1)'}, "
              f"neurotransmitter={nt_col or '(none found, all excitatory)'}")

        # --- Map biological root IDs to sequential integers ---
        all_ids = pd.unique(df[[pre_col, post_col]].to_numpy().ravel())
        self.root_id_to_idx = pd.Series(np.arange(len(all_ids), dtype=np.int64), index=all_ids)
        self.idx_to_root_id = all_ids
        self.n_neurons = len(all_ids)
        pre_idx = self.root_id_to_idx.loc[df[pre_col].to_numpy()].to_numpy()
        post_idx = self.root_id_to_idx.loc[df[post_col].to_numpy()].to_numpy()

        weights = (df[weight_col].to_numpy(dtype=np.float32)
                   if weight_col else np.ones(len(df), dtype=np.float32))

        if nt_col:
            nt = df[nt_col].astype(str).str.upper()
            # Simplifying assumption: GABA and glutamate treated as inhibitory
            # (glutamate is inhibitory at many fly CNS synapses, unlike in
            # vertebrates), everything else (ACh, dopamine, serotonin,
            # octopamine, unknown) treated as excitatory. This is a coarse
            # approximation, not a claim of biological precision.
            inhibitory = nt.str.contains("GABA") | nt.str.contains("GLUT")
            sign = np.where(inhibitory.to_numpy(), -1.0, 1.0)
        else:
            sign = np.ones(len(df), dtype=np.float32)

        signed_weights = weights * sign

        # --- Build the sparse adjacency tensor (COO = mutable source of truth) ---
        self.indices = torch.tensor(np.vstack([pre_idx, post_idx]), dtype=torch.long, device=device)
        self.values = torch.tensor(signed_weights, dtype=torch.float32, device=device)
        self._rebuild_csr()  # builds the fast CSR snapshot decide() actually uses

        self._select_io_pools(pool_size)

    # -- column auto-detection -------------------------------------------------
    @staticmethod
    def _detect_columns(df):
        lower_map = {c.lower(): c for c in df.columns}

        def find(*candidates):
            for cand in candidates:
                if cand in lower_map:
                    return lower_map[cand]
            return None

        pre_col = find("pre_root_id", "pre_pt_root_id", "pre", "presyn_id")
        post_col = find("post_root_id", "post_pt_root_id", "post", "postsyn_id")
        weight_col = find("syn_count", "weight", "count", "n_syn", "synapse_count")
        nt_col = find("nt_type", "neurotransmitter", "predicted_nt_type", "nt")

        if pre_col is None or post_col is None:
            raise ValueError(
                f"Could not find pre/post root-id columns in {list(df.columns)}. "
                "Expected something like 'pre_root_id' and 'post_root_id' "
                "(the FlyWire 'Connections (Filtered)' export schema). "
                "Open the CSV and check its header, then adjust "
                "FlyBrain._detect_columns() if your export uses different names."
            )
        return pre_col, post_col, weight_col, nt_col

    def _rebuild_csr(self):
        """(Re)builds the CSR-format transposed adjacency from the current
        COO indices/values. This is the expensive step (~1-1.5s at real
        dataset scale) -- callers that need it off the main/game thread
        should run this inside a background thread, not call it directly
        during gameplay."""
        coo = torch.sparse_coo_tensor(
            self.indices, self.values, (self.n_neurons, self.n_neurons)
        ).coalesce()
        self.adj_t_csr = coo.t().coalesce().to_sparse_csr()

    def _select_io_pools(self, pool_size):
        out_deg = torch.zeros(self.n_neurons, device=self.device)
        in_deg = torch.zeros(self.n_neurons, device=self.device)
        ones = torch.ones(self.indices.shape[1], device=self.device)
        out_deg.index_add_(0, self.indices[0], ones)
        in_deg.index_add_(0, self.indices[1], ones)

        sensory_ranked = torch.argsort(out_deg - in_deg, descending=True)
        motor_ranked = torch.argsort(in_deg - out_deg, descending=True)

        sensory_pool = sensory_ranked[:pool_size]
        # keep motor pool disjoint from the sensory pool
        sensory_set = set(sensory_pool.tolist())
        motor_pool_list = [i for i in motor_ranked.tolist() if i not in sensory_set][:pool_size]

        # IMPORTANT: the motor pool is ranked by (in_deg - out_deg), a smooth
        # monotonic score. Slicing it into 4 CONTIGUOUS rank bands (neurons
        # 0-49 -> ability 0, 50-99 -> ability 1, ...) gives each ability group
        # a systematically different resting/baseline activation once you
        # accumulate signal over several propagation hops -- one band ends up
        # permanently "hotter" than the others under the tanh dynamics, so
        # its ability wins argmax for essentially every input regardless of
        # game state (confirmed empirically: index 2 / Dodge won 8/8 varied
        # test inputs before this fix). Shuffling the pool before slicing
        # breaks up that rank-correlated structure so each group is a random
        # sample of similarly-ranked motor neurons instead of a distinct band.
        random.shuffle(motor_pool_list)
        motor_pool = torch.tensor(motor_pool_list, dtype=torch.long, device=self.device)

        group = pool_size // 4
        self.sensory_groups = sensory_pool[: group * 4].reshape(4, group)
        self.motor_groups = motor_pool[: group * 4].reshape(4, group)

        print(f"[brain] sensory pool: {len(sensory_pool)} neurons, "
              f"motor pool: {len(motor_pool)} neurons "
              f"({group} per ability/signal)")

        # -- baseline calibration -------------------------------------------
        # Even after shuffling, each ability's group is a different random
        # sample of neurons and can have a different resting activation under
        # neutral input. Calibrate by running one neutral-input decision and
        # storing its raw logits as a per-ability baseline; decide() then
        # reports each ability's signal as a DELTA from its own resting state
        # rather than comparing raw magnitudes across structurally different
        # neuron pools.
        self.motor_baseline = torch.zeros(4, device=self.device)
        _, baseline_raw = self._connectome_signal(
            boss_attacking=0, boss_defending=0,
            boss_health_frac=0.5, fly_health_frac=0.5,
        )
        self.motor_baseline = baseline_raw.to(self.device)
        print(f"[brain] motor baseline (neutral input): {self.motor_baseline.tolist()}")

        # -- trainable policy readout ----------------------------------------
        # The connectome above is the "reservoir": a large, fixed, never-
        # trained biological network (apply_pain/apply_harmony perturb its
        # raw weights for thematic/consequence reasons, but that's noise
        # injection, not learning). This small readout is the ONLY part of
        # the brain that actually learns: an 8 -> 4 linear map from
        # [raw sensory signal (4) ++ baseline-subtracted connectome signal
        # (4)] to ability logits, trained via REINFORCE (see learn_from_life)
        # using the Watcher's per-life score as the reward. It starts as an
        # exact pass-through of the connectome signal (identity on that half,
        # zero elsewhere) so day-one behavior is unchanged; only repeated
        # play shifts it away from that.
        feature_dim = 8
        self.readout_W = torch.zeros(feature_dim, 4, device=self.device, requires_grad=True)
        with torch.no_grad():
            self.readout_W[4:, :] = torch.eye(4, device=self.device)
        self.readout_b = torch.zeros(4, device=self.device, requires_grad=True)
        self.optimizer = optim.Adam([self.readout_W, self.readout_b], lr=LEARNING_RATE)
        self.reward_baseline = 0.0
        self.total_updates = 0
        self.last_reward = None
        self.last_advantage = None
        self.reward_history = deque(maxlen=SCORE_HISTORY_LEN)
        self._traj_lock = threading.Lock()
        self._trajectory = []  # log-probs of actions taken so far this life

    # -- fixed connectome forward pass (never trained) ----------------------
    def _connectome_signal(self, boss_attacking, boss_defending, boss_health_frac, fly_health_frac):
        """Runs the actual sparse message-passing propagation through the
        real connectome and pools the 4 motor groups back out. This is the
        expensive, biologically-grounded part of the brain, and it never
        receives gradients -- it's deliberately kept as a fixed random
        feature extractor ("reservoir"); only the small readout in decide()
        learns. Returns (raw_signal_4vec, raw_motor_pool_4vec), both plain
        (non-autograd) tensors.
        """
        # Snapshot the current CSR tensor once. A background rebuild (see
        # apply_pain/apply_harmony) may replace self.adj_t_csr with a new
        # object at any time, but simple attribute read/write is atomic
        # under the GIL, so this local reference stays valid and consistent
        # for the whole decision even if a swap happens mid-computation --
        # no lock needed here (verified: the lock only ever needs to guard
        # the *mutation* of self.values, which apply_pain/apply_harmony do).
        adj_t_csr = self.adj_t_csr
        n = self.n_neurons

        with torch.no_grad():
            state = torch.zeros(n, device=self.device)
            signal = torch.tensor(
                [float(boss_attacking), float(boss_defending),
                 float(boss_health_frac), float(fly_health_frac)],
                device=self.device,
            )
            for i in range(4):
                state[self.sensory_groups[i]] = signal[i]

            x = state
            accum = torch.zeros(n, device=self.device)
            for _ in range(self.num_hops):
                x = torch.sparse.mm(adj_t_csr, x.unsqueeze(1)).squeeze(1)
                x = torch.tanh(x * 0.05)
                accum = accum + x

            raw = accum[self.motor_groups].mean(dim=1)
        return signal, raw

    # -- forward decision --------------------------------------------------
    def decide(self, boss_attacking, boss_defending, boss_health_frac, fly_health_frac):
        """
        Feeds the boss's state (attacking, defending, health) plus the fly's
        own health into the sensory groups, propagates it through the fixed
        connectome for several hops, then passes [raw signal ++ baseline-
        subtracted connectome readout] through the small TRAINABLE readout
        (see __init__) to get the final ability logits. Returns
        (ability_index, logits_tensor). Every call also appends this
        decision's log-probability to the current life's trajectory, which
        learn_from_life() later turns into a policy-gradient update.
        """
        signal, raw = self._connectome_signal(
            boss_attacking, boss_defending, boss_health_frac, fly_health_frac
        )
        brain_signal = (raw - self.motor_baseline).detach()
        features = torch.cat([signal.detach(), brain_signal])

        logits = features @ self.readout_W + self.readout_b

        # Sample rather than hard-argmax (see DECISION_TEMPERATURE comment):
        # keeps the network's preference dominant while avoiding a
        # deterministic stuck state when the sensory input stops changing.
        probs = torch.softmax(logits / DECISION_TEMPERATURE, dim=0)
        ability_idx = int(torch.multinomial(probs, 1).item())
        log_prob = torch.log(probs[ability_idx] + 1e-8)

        with self._traj_lock:
            self._trajectory.append(log_prob)

        return ability_idx, logits.detach().cpu()

    # -- genuine learning: policy-gradient update on the readout only -------
    def learn_from_life(self, reward):
        """Called once a life ends (death or win) with a scalar reward (the
        Watcher's normalized score for a death, or WIN_REWARD for a win).
        This is real credit assignment via REINFORCE with a running-average
        baseline (reduces variance without needing a separate critic
        network): every decision made during the life is nudged to be more
        likely (if the life scored above the recent average) or less likely
        (if below), in proportion to how surprising/confident that decision
        was. It's intentionally simple -- one reward shared across the whole
        episode, no discounting, no per-step credit assignment -- but it is
        genuine gradient descent driven by outcome, unlike apply_pain/
        apply_harmony's undirected noise injection on the connectome itself
        (which still runs separately, for the thematic consequence system).
        Returns a stats dict for display, or None if no decisions were made.
        """
        with self._traj_lock:
            trajectory, self._trajectory = self._trajectory, []
        if not trajectory:
            return None

        advantage = reward - self.reward_baseline
        self.reward_baseline = 0.9 * self.reward_baseline + 0.1 * reward

        loss = -advantage * torch.stack(trajectory).mean()
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        self.total_updates += 1
        self.last_reward = reward
        self.last_advantage = advantage
        self.reward_history.append(reward)

        return {
            "reward": reward,
            "advantage": advantage,
            "baseline": self.reward_baseline,
            "updates": self.total_updates,
            "decisions": len(trajectory),
        }

    # -- consequence system --------------------------------------------------
    # Both of these mutate weights then rebuild the CSR snapshot, which takes
    # over a second at this dataset's scale. They run that rebuild on a
    # background thread and return immediately -- see the FlyBrain docstring
    # for why calling _rebuild_csr() synchronously here would visibly freeze
    # the game window, not just the intended freeze-screen overlay.
    def _dispatch_rebuild(self, mutate_fn):
        def _work():
            with self._mutate_lock:
                mutate_fn()
                self._rebuild_csr()
        t = threading.Thread(target=_work, daemon=True)
        t.start()
        self._pending_rebuilds.append(t)

    def apply_pain(self, intensity=25.0):
        """Loss state: violently scramble the weights (simulated aversive
        signal). No-op once the brain has been locked into harmony."""
        if self.locked:
            return

        def mutate():
            noise_scale = self.values.abs().mean().clamp(min=1e-3) * intensity
            noise = (torch.rand_like(self.values) - 0.5) * noise_scale
            self.values = self.values + noise

        self._dispatch_rebuild(mutate)

    def apply_harmony(self, reward_scale=1.6):
        """Win state: lock the weights into their current (winning) pattern
        and amplify it as a large positive reward signal. Once locked,
        apply_pain() no longer perturbs this brain."""
        def mutate():
            self.values = self.values * reward_scale
            self.locked = True

        self._dispatch_rebuild(mutate)

    def shutdown(self):
        """Joins any in-flight pain/harmony rebuild threads. Call before the
        process exits, for the same reason FlyBrainThread.stop() joins its
        worker: letting the interpreter tear down while a torch op is still
        running on a background thread can abort the whole process."""
        for t in self._pending_rebuilds:
            t.join(timeout=5.0)


def describe_sample_graph(brain: FlyBrain, sample_edges=2000):
    """Optional debug helper using networkx over a small random EDGE sample
    (never the full connectome -- see the networkx import comment above)."""
    idx = brain.indices.t().tolist()
    sample = random.sample(idx, min(sample_edges, len(idx)))
    g = nx.DiGraph()
    g.add_edges_from(sample)
    print(f"[debug] sample graph: {g.number_of_nodes()} nodes, "
          f"{g.number_of_edges()} edges, "
          f"weakly connected components: {nx.number_weakly_connected_components(g)}")


class FlyBrainThread:
    """Runs FlyBrain.decide() on its own cadence in a background thread so
    decisions never cause a dropped render frame. With the CSR adjacency,
    one decision measured ~30-40ms on a 2-core test machine against the
    real 3.7M-edge dataset (down from ~900ms before that fix) -- comfortably
    inside DECISION_INTERVAL, likely faster still on a machine with more
    cores. torch's sparse ops also release the GIL during the actual
    matmul, so this does not meaningfully starve the main pygame loop
    (verified with a synthetic load test before shipping this)."""

    def __init__(self, brain: FlyBrain, interval=DECISION_INTERVAL):
        self.brain = brain
        self.interval = interval
        self._decision_count = 0
        self._latest = (0, torch.zeros(4), 0)  # ability_idx, logits, decision_count
        self._lock = threading.Lock()
        self._boss_state_provider = lambda: (0, 0, 1.0, 1.0)
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self, boss_state_provider):
        self._boss_state_provider = boss_state_provider
        self._thread.start()

    def stop(self):
        """Signals the worker to stop and BLOCKS until it has actually
        exited. This matters: if the main thread proceeds to pygame.quit()
        / process exit while this daemon thread is still mid torch
        computation, the interpreter can tear down native threadpools out
        from under it and abort the whole process ('terminate called
        without an active exception'). Confirmed by reproducing it directly
        during testing -- always join a worker thread that touches torch
        before letting the process end."""
        self._stop = True
        self._thread.join(timeout=5.0)

    def _run(self):
        while not self._stop:
            attacking, defending, boss_hp_frac, fly_hp_frac = self._boss_state_provider()
            ability_idx, logits = self.brain.decide(attacking, defending, boss_hp_frac, fly_hp_frac)
            self._decision_count += 1
            with self._lock:
                self._latest = (ability_idx, logits, self._decision_count)
            # sleep in small slices so a stop() request is picked up quickly
            # instead of waiting out a full DECISION_INTERVAL
            slept = 0.0
            while slept < self.interval and not self._stop:
                time.sleep(0.05)
                slept += 0.05

    def latest(self):
        """Returns (ability_idx, logits, decision_count). decision_count
        increments on every decision even when the chosen ability repeats,
        so callers that want to plot a moving/live series (rather than only
        react to ability changes) can detect "a new decision landed" by
        watching this counter instead of the ability index."""
        with self._lock:
            return self._latest


# ==============================================================================
# PART 2: GAME LOGIC & VISUALS  (Pygame)
#
# Framework choice: Pygame. It's pure Python + SDL, installs with one pip
# command, and needs no native SDK/graphics-driver setup the way Ursina or
# Panda3D sometimes do -- which matters given the "broken configuration"
# starting point. It's rendered here as animated 2D sprites (procedural fly
# animation + the boss texture), not true 3D, in exchange for being the most
# robust thing to get running in a flaky VS Code environment today.
# ==============================================================================

def load_image_safe(path, size):
    """Loads opponent.png if present; falls back to a placeholder rectangle
    (with a clear on-screen label) if it's missing, so the game still runs
    even before you've added the real asset."""
    if os.path.exists(path):
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(img, size)
        except Exception as exc:
            print(f"[assets] Failed to load {path}: {exc}. Using placeholder.")
    else:
        print(f"[assets] {path} not found. Using placeholder boss texture. "
              f"Drop your real file at this path to replace it.")
    placeholder = pygame.Surface(size, pygame.SRCALPHA)
    placeholder.fill((120, 30, 40, 255))
    pygame.draw.rect(placeholder, (200, 60, 70), placeholder.get_rect(), width=4)
    return placeholder


def load_sound_safe(path):
    if os.path.exists(path):
        try:
            return pygame.mixer.Sound(path)
        except Exception as exc:
            print(f"[assets] Failed to load {path}: {exc}. Death sound disabled.")
    else:
        print(f"[assets] {path} not found. Death sound disabled until you add it.")
    return None


# ==============================================================================
# FAKE-3D SHADING -- still plain 2D Pygame (no mesh, no engine, no extra
# dependency), but two cheap tricks that read as "volume" instead of flat
# color: (1) a pre-baked directional-light gradient, multiply-blended onto a
# shape so it shades like a lit sphere instead of a flat disc, and (2) a
# drop shadow on the "ground" beneath each sprite, which is one of the
# strongest depth cues the eye picks up on even with zero real geometry.
# ==============================================================================
_SPHERE_SHADE_CACHE = {}


def _get_sphere_shade(size=96):
    """Lazily builds (and caches) a small RGB gradient surface: bright
    upper-left (fake key light), darker lower-right (fake core shadow) --
    the classic "shade a circle to make it look like a ball" trick. Built
    once with numpy, then cheaply smoothscaled to whatever size is needed
    at draw time."""
    if size in _SPHERE_SHADE_CACHE:
        return _SPHERE_SHADE_CACHE[size]

    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    cx, cy = size / 2.0, size / 2.0
    r = size / 2.0
    # fake light source offset toward the upper-left of the shape
    lx, ly = cx - 0.4 * size, cy - 0.4 * size
    dist_light = np.sqrt((xs - lx) ** 2 + (ys - ly) ** 2) / (r * 1.4)
    dist_center = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r

    shade = np.clip(1.45 - dist_light, 0.45, 1.3)          # key-light falloff
    shade *= np.clip(1.1 - 0.3 * dist_center, 0.55, 1.1)   # subtle rim darkening
    val = np.clip(shade * 255.0, 0, 255).astype(np.uint8)

    rgb = np.stack([val, val, val], axis=-1)
    surf = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
    _SPHERE_SHADE_CACHE[size] = surf
    return surf


def draw_shaded_ellipse(screen, color, rect):
    """Draws an ellipse pre-shaded with the fake key-light gradient above,
    so it reads as a lit sphere/body instead of a flat color blob."""
    w, h = max(1, rect.width), max(1, rect.height)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(surf, color, pygame.Rect(0, 0, w, h))
    shade = pygame.transform.smoothscale(_get_sphere_shade(), (w, h))
    # RGBA_MULT scales this surface's RGB (and alpha) by the shade surface's
    # own values -- since shade has full alpha everywhere, the ellipse's
    # existing alpha mask (opaque inside, transparent outside) is preserved,
    # only the color brightness inside the ellipse changes.
    surf.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(surf, rect.topleft)


def shade_image(image):
    """Same trick as draw_shaded_ellipse, but for an arbitrary (already
    alpha-having) image such as the boss texture: multiply-blends the
    key-light gradient on top so a flat sprite picks up a sense of volume.
    Returns a shaded copy -- callers still blit further overlays (like
    hit-flash) on top of that, same as before this was added."""
    shaded = image.copy()
    shade = pygame.transform.smoothscale(_get_sphere_shade(), image.get_size())
    shaded.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return shaded


def draw_drop_shadow(screen, cx, ground_cy, width, height, alpha=110):
    """A soft dark ellipse on the ground beneath a sprite -- one of the
    cheapest, strongest depth cues available in flat 2D rendering."""
    shadow = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, alpha), shadow.get_rect())
    rect = shadow.get_rect(center=(cx, ground_cy))
    screen.blit(shadow, rect)


class Boss:
    def __init__(self, texture, x, y):
        self.texture = texture
        self.rect = texture.get_rect(center=(x, y))
        self.max_hp = BOSS_MAX_HP
        self.hp = self.max_hp
        self.state = "idle"       # idle -> telegraph -> attacking -> idle / defending
        self.timer = random.uniform(*BOSS_IDLE_TIME_RANGE)
        self.pulse = 0.0
        self.hit_flash = 0.0      # visual feedback: set whenever the fly lands a hit
        self.hit_resolved = False  # whether THIS attack has already dealt its damage
        self.bob_phase = random.uniform(0, math.tau)  # idle bob so it never looks frozen
        self.parry_window_hit = False  # was Parry held at any point during THIS
                                        # telegraph? (see PARRY MECHANIC constants)

    def reset(self):
        self.hp = self.max_hp
        self.state = "idle"
        self.timer = random.uniform(*BOSS_IDLE_TIME_RANGE)
        self.hit_flash = 0.0
        self.hit_resolved = False
        self.parry_window_hit = False

    def on_hit(self):
        """Call when the fly's attack (or a perfect-parry counter) actually
        lands on the boss."""
        self.hit_flash = BOSS_HIT_FLASH_DURATION

    def register_parry_attempt(self):
        """Call every frame the fly is holding Parry while this boss is in
        its telegraph (warning) window. Anticipating the telegraph -- not
        just reacting once the hit is already live -- is what makes the
        difference between a perfect parry and an ordinary dodge."""
        self.parry_window_hit = True

    @property
    def is_enraged(self):
        """See BOSS_ENRAGE_* constants: below this HP fraction the boss hits
        harder and attacks faster, like a real boss-fight second phase."""
        return (self.hp / self.max_hp) < BOSS_ENRAGE_HP_FRAC

    def update(self, dt):
        speed_mult = BOSS_ENRAGE_SPEED_MULT if self.is_enraged else 1.0
        self.timer -= dt / speed_mult
        self.pulse = max(0.0, self.pulse - dt * 1.3)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.bob_phase += dt * 1.1
        if self.timer <= 0:
            if self.state == "idle":
                self.state = ("defending" if random.random() < BOSS_DEFEND_CHANCE
                              else "telegraph")
                self.timer = BOSS_TELEGRAPH_TIME if self.state == "telegraph" else BOSS_DEFEND_TIME
                if self.state == "telegraph":
                    self.parry_window_hit = False  # a fresh attempt begins
            elif self.state == "telegraph":
                self.state = "attacking"
                self.timer = BOSS_ATTACK_TIME
                self.pulse = 1.0
                self.hit_resolved = False  # a fresh attack window: allow one hit
            elif self.state == "attacking":
                self.state = "idle"
                self.timer = random.uniform(*BOSS_IDLE_TIME_RANGE)
            elif self.state == "defending":
                self.state = "idle"
                self.timer = random.uniform(*BOSS_IDLE_TIME_RANGE)

    @property
    def is_attacking(self):
        return self.state == "attacking"

    @property
    def is_defending(self):
        return self.state == "defending"

    def draw(self, screen):
        # Idle bob so the boss always visibly moves even between attacks --
        # previously it could look completely frozen for 1-2 seconds at a
        # stretch between state changes.
        bob_y = math.sin(self.bob_phase) * 4
        scale = 1.0 + 0.12 * self.pulse
        w, h = self.texture.get_size()

        # Drop shadow on the "ground" beneath it -- doesn't move with the
        # bob, so the boss reads as floating slightly above its own shadow
        # instead of just sliding up and down in place.
        draw_drop_shadow(screen, self.rect.centerx, self.rect.bottom - 6,
                          int(w * 0.7), int(h * 0.22), alpha=100)

        img = pygame.transform.smoothscale(self.texture, (int(w * scale), int(h * scale)))
        img = shade_image(img)  # fake key-light volume shading (still plain 2D)
        rect = img.get_rect(center=(self.rect.centerx, self.rect.centery + bob_y))

        if self.hit_flash > 0:
            # Bright white flash the instant it takes a hit -- previously
            # the "attacking" pulse was the only feedback and it collapsed
            # to ~2 render frames (see update()/hit_resolved fix), making a
            # landed hit essentially invisible.
            flashed = img.copy()
            flash_surf = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            flash_surf.fill((255, 255, 255, min(255, int(200 * (self.hit_flash / BOSS_HIT_FLASH_DURATION)))))
            flashed.blit(flash_surf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(flashed, rect)
        elif self.state == "defending":
            tint = pygame.Surface(rect.size, pygame.SRCALPHA)
            tint.fill((80, 120, 220, 70))
            screen.blit(img, rect)
            screen.blit(tint, rect)
        elif self.state == "telegraph":
            outline = pygame.Surface(rect.size, pygame.SRCALPHA)
            # Cyan instead of red once the fly has committed to Parry during
            # this telegraph -- a visible "this is about to be punished" tell.
            outline_color = (90, 220, 240, 200) if self.parry_window_hit else (255, 60, 60, 160)
            pygame.draw.rect(outline, outline_color, outline.get_rect(), width=8)
            screen.blit(img, rect)
            screen.blit(outline, rect)
        elif self.state == "attacking":
            outline = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(outline, (255, 140, 0, 180), outline.get_rect(), width=10)
            screen.blit(img, rect)
            screen.blit(outline, rect)
        else:
            screen.blit(img, rect)

        if self.is_enraged:
            # A pulsing red outline on top of whatever else is drawn, so
            # "enraged" reads clearly no matter what state it's paired with.
            enrage_alpha = int(90 + 70 * (0.5 + 0.5 * math.sin(self.bob_phase * 3)))
            enrage_outline = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(enrage_outline, (255, 20, 20, enrage_alpha),
                              enrage_outline.get_rect(), width=5)
            screen.blit(enrage_outline, rect)

        draw_health_bar(screen, self.rect.centerx, self.rect.top - 30, 160, 16,
                         self.hp / self.max_hp, (200, 40, 50))

        state_label = {"idle": "", "telegraph": "WINDING UP...",
                       "attacking": "ATTACK!", "defending": "DEFENDING"}[self.state]
        if self.is_enraged:
            state_label = (state_label + "  [ENRAGED]") if state_label else "ENRAGED"
        if state_label:
            font = pygame.font.SysFont("arial", 18, bold=True)
            color = (255, 210, 60) if self.state == "telegraph" else (
                255, 120, 60) if self.state == "attacking" else (140, 180, 255)
            if self.is_enraged:
                color = (255, 60, 60)
            txt = font.render(state_label, True, color)
            screen.blit(txt, (self.rect.centerx - txt.get_width() // 2, self.rect.top - 52))


class Fly:
    """A procedurally animated fly sprite (no image asset was provided for
    it, so it's drawn each frame with pygame primitives). Its animation
    state reflects whichever ability the brain most recently chose."""

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.home = (x, y)
        self.max_hp = FLY_MAX_HP
        self.hp = self.max_hp
        self.current_ability = 0
        self.action_timer = 0.0
        self.label_timer = 0.0    # separate, longer-lived than action_timer so the
        self.wing_phase = 0.0     # ability name is actually readable, not a 1-frame flash
        self.hurt_flash = 0.0
        self.impact_ring = 0.0    # 0..1 progress of an expanding "landed a hit" ring
        self.bob_phase = random.uniform(0, math.tau)

    def reset(self):
        self.hp = self.max_hp
        self.x, self.y = self.home
        self.action_timer = 0.0
        self.label_timer = 0.0
        self.impact_ring = 0.0

    def trigger_ability(self, ability_idx):
        self.current_ability = ability_idx
        self.action_timer = 0.5
        self.label_timer = LABEL_DISPLAY_TIME  # tied to DECISION_INTERVAL --
        # see its definition -- so the label reads clearly before it changes

    def take_damage(self, amount):
        self.hp = max(0, self.hp - amount)
        self.hurt_flash = 0.45

    def on_landed_hit(self):
        """Call when one of this fly's attacks actually connects."""
        self.impact_ring = 1.0

    def update(self, dt):
        self.wing_phase += dt * 22
        self.bob_phase += dt * 1.6
        self.action_timer = max(0.0, self.action_timer - dt)
        self.label_timer = max(0.0, self.label_timer - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.impact_ring = max(0.0, self.impact_ring - dt * 0.9)
        # lunge toward the boss on attacks, retreat on dodge -- made larger
        # and held for the ability's full window so it actually reads as
        # motion instead of a barely-there twitch
        target_dx = 0
        if self.action_timer > 0:
            if self.current_ability == 0:      # light attack
                target_dx = 55
            elif self.current_ability == 1:    # heavy attack
                target_dx = 95
            elif self.current_ability == 2:    # dodge
                target_dx = -70
        target_dy = math.sin(self.bob_phase) * 6  # idle bob so it's never static
        self.x += (self.home[0] + target_dx - self.x) * min(1.0, dt * 12)
        self.y += (self.home[1] + target_dy - self.y) * min(1.0, dt * 12)

    def draw(self, screen):
        body_color = ABILITY_COLORS[self.current_ability] if self.action_timer > 0 else (230, 210, 40)
        if self.hurt_flash > 0:
            body_color = (255, 60, 60)

        cx, cy = int(self.x), int(self.y)
        wing_offset = math.sin(self.wing_phase) * 12

        # Drop shadow at the fly's home height -- since the body bobs above
        # this fixed line, the fly reads as hovering rather than pinned flat
        # to the screen. Shrinks/fades slightly the higher it bobs.
        rise = max(0.0, self.home[1] - self.y)
        shadow_scale = max(0.6, 1.0 - rise / 20.0)
        draw_drop_shadow(screen, int(self.home[0]), int(self.home[1]) + 20,
                          int(34 * shadow_scale), int(10 * shadow_scale), alpha=90)

        # expanding ring when an attack lands -- makes "the fly just hit
        # something" unmistakable even at a glance
        if self.impact_ring > 0:
            radius = int((1.0 - self.impact_ring) * 30) + 6
            alpha = int(200 * self.impact_ring)
            ring_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (255, 255, 255, alpha),
                                (radius + 2, radius + 2), radius, width=3)
            screen.blit(ring_surf, (cx - radius - 2, cy - radius - 2))

        # wings
        for side in (-1, 1):
            wing_rect = pygame.Rect(0, 0, 26, 12)
            wing_rect.center = (cx + side * 12, cy - 8 + wing_offset * side * 0.3)
            wing_surf = pygame.Surface(wing_rect.size, pygame.SRCALPHA)
            pygame.draw.ellipse(wing_surf, (220, 240, 255, 170), wing_surf.get_rect())
            shade = pygame.transform.smoothscale(_get_sphere_shade(), wing_rect.size)
            wing_surf.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(wing_surf, wing_rect)

        # body -- pre-shaded like a lit sphere instead of a flat ellipse,
        # plus a small highlight dot for a "shiny carapace" touch
        draw_shaded_ellipse(screen, body_color, pygame.Rect(cx - 15, cy - 10, 30, 20))
        highlight = pygame.Surface((10, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(highlight, (255, 255, 255, 90), highlight.get_rect())
        screen.blit(highlight, (cx - 9, cy - 8))
        pygame.draw.circle(screen, (30, 30, 30), (cx + 13, cy - 4), 5)  # eye
        pygame.draw.circle(screen, (90, 90, 90), (cx + 14, cy - 5), 2)  # eye glint

        draw_health_bar(screen, cx, cy - 42, 90, 10, self.hp / self.max_hp, (60, 200, 90))

        if self.label_timer > 0:
            font = pygame.font.SysFont("arial", 18, bold=True)
            alpha = min(255, int(255 * (self.label_timer / 0.3)))
            txt = font.render(ABILITY_NAMES[self.current_ability], True,
                               ABILITY_COLORS[self.current_ability])
            txt.set_alpha(alpha)
            screen.blit(txt, (cx - txt.get_width() // 2, cy + 22))


def draw_health_bar(screen, cx, top_y, width, height, frac, color):
    frac = max(0.0, min(1.0, frac))
    rect = pygame.Rect(0, 0, width, height)
    rect.center = (cx, top_y)
    pygame.draw.rect(screen, (40, 40, 40), rect)
    fill = rect.copy()
    fill.width = int(width * frac)
    pygame.draw.rect(screen, color, fill)
    pygame.draw.rect(screen, (10, 10, 10), rect, width=2)


# ==============================================================================
# THE WATCHER (Critic)
#
# Rather than the fly always getting the same fixed "disturbing pain" no
# matter how the attempt went, the Watcher observes each death and scores it
# on three things: how long the fly survived, how much damage it dealt to
# the boss, and how many boss attacks it successfully dodged. That score
# scales the pain intensity actually applied: a fly that is clearly getting
# better (surviving longer / hitting harder / dodging more, especially versus
# its own last attempt) gets a lighter penalty, while a fly that stood still
# and died almost instantly -- no damage dealt, no dodges, dead in under a
# second -- gets the maximum penalty regardless of history. This is meant to
# behave like a shaped reward signal rather than a flat punishment.
# ==============================================================================
class Watcher:
    def __init__(self):
        self.history = deque(maxlen=SCORE_HISTORY_LEN)  # dicts, oldest first
        self.best_score = 0.0
        self.last_score = None

    def score_life(self, time_survived, damage_dealt, successful_dodges,
                    successful_parries, boss_max_hp):
        """Scores one death-loop attempt and returns a dict including the
        pain_scale to multiply BASE_PAIN_INTENSITY by (in [MIN_PAIN_SCALE, 1.0]).
        Perfect parries (see PARRY MECHANIC constants) count on their own
        dimension, separate from ordinary reactive dodges -- they're harder
        to land, so REFERENCE_PARRY_COUNT is deliberately lower than
        REFERENCE_DODGE_COUNT, meaning even one or two genuinely earn credit."""
        norm_time = min(time_survived / REFERENCE_SURVIVAL_SECONDS, 1.0)
        norm_damage = min(damage_dealt / boss_max_hp, 1.0)
        norm_dodges = min(successful_dodges / REFERENCE_DODGE_COUNT, 1.0)
        norm_parries = min(successful_parries / REFERENCE_PARRY_COUNT, 1.0)
        score = (norm_time + norm_damage + norm_dodges + norm_parries) / 4.0

        stood_still_and_died = (
            time_survived < STILL_DEATH_TIME
            and damage_dealt < STILL_DEATH_DAMAGE
            and successful_dodges == 0
            and successful_parries == 0
        )

        if stood_still_and_died:
            pain_scale = 1.0  # maximum pain, no matter what happened before
        else:
            baseline = self.last_score if self.last_score is not None else 0.0
            improvement = score - baseline
            # Both absolute competence and improvement-over-last-attempt earn
            # leniency; either one alone is enough to meaningfully reduce pain.
            leniency = max(0.0, min(1.0, score * 0.6 + max(improvement, 0.0) * 0.8))
            pain_scale = max(MIN_PAIN_SCALE, 1.0 - leniency)

        record = {
            "time_survived": time_survived,
            "damage_dealt": damage_dealt,
            "dodges": successful_dodges,
            "parries": successful_parries,
            "score": score,
            "pain_scale": pain_scale,
            "stood_still": stood_still_and_died,
        }
        self.history.append(record)
        self.best_score = max(self.best_score, score)
        self.last_score = score
        return record


def draw_sidebar(screen, fonts, logit_history, current_logits, decisions_per_sec,
                  brain_locked, lives_lost, wins, watcher, last_record,
                  ability_counts, current_life, learning_stats, reward_history,
                  total_updates, is_playing):
    """The left-side panel: moving/live statistics on the fly's brain --
    its current motor output, that output's history over time, the ongoing
    life's running stats, cumulative ability usage, the Watcher's scoring of
    recent lives, and the trainable readout's learning progress."""
    title_font, label_font, small_font = fonts
    panel_rect = pygame.Rect(0, 0, SIDEBAR_W, SCREEN_H)
    pygame.draw.rect(screen, (14, 14, 22), panel_rect)
    pygame.draw.line(screen, (60, 60, 80), (SIDEBAR_W, 0), (SIDEBAR_W, SCREEN_H), 2)

    pad = 14
    inner_w = SIDEBAR_W - 2 * pad
    y = 14

    title = title_font.render("FLY BRAIN MONITOR", True, (230, 230, 240))
    screen.blit(title, (pad, y))
    y += title.get_height() + 12

    # --- current motor output (live bars) ---
    screen.blit(label_font.render("Motor output (live)", True, (170, 170, 190)), (pad, y))
    y += 20
    if current_logits is not None and len(current_logits) == 4:
        lo, hi = min(current_logits), max(current_logits)
        span = max(hi - lo, 1e-6)
        for i in range(4):
            bar_h = 16
            frac = max(0.03, (current_logits[i] - lo) / span)
            rect_bg = pygame.Rect(pad, y, inner_w, bar_h)
            pygame.draw.rect(screen, (35, 35, 48), rect_bg)
            pygame.draw.rect(screen, ABILITY_COLORS[i], pygame.Rect(pad, y, int(inner_w * frac), bar_h))
            txt = small_font.render(ABILITY_NAMES[i], True, (235, 235, 235))
            screen.blit(txt, (pad + 4, y + 1))
            y += bar_h + 4
    y += 8

    # --- moving history chart: this is the "brain activity over time" view ---
    screen.blit(label_font.render("Motor output over time", True, (170, 170, 190)), (pad, y))
    y += 20
    chart_h = 110
    chart_rect = pygame.Rect(pad, y, inner_w, chart_h)
    pygame.draw.rect(screen, (10, 10, 16), chart_rect)
    pygame.draw.rect(screen, (50, 50, 65), chart_rect, width=1)
    if len(logit_history) >= 2:
        flat = [v for row in logit_history for v in row]
        lo, hi = min(flat), max(flat)
        span = max(hi - lo, 1e-6)
        n = len(logit_history)
        for i in range(4):
            points = []
            for j, row in enumerate(logit_history):
                px = chart_rect.x + int(j / max(n - 1, 1) * chart_rect.w)
                py = chart_rect.bottom - int((row[i] - lo) / span * chart_rect.h)
                points.append((px, py))
            pygame.draw.lines(screen, ABILITY_COLORS[i], False, points, 2)
    y += chart_h + 14

    # --- numeric readouts ---
    for line in (
        f"Decisions/sec: {decisions_per_sec:.1f}  (every {DECISION_INTERVAL:.1f}s)",
        f"Brain locked (harmony): {'YES' if brain_locked else 'no'}",
        f"Lives lost: {lives_lost}    Wins: {wins}",
    ):
        txt = small_font.render(line, True, (210, 210, 220))
        screen.blit(txt, (pad, y))
        y += txt.get_height() + 4
    y += 10

    # --- current life (live, while playing) ---
    screen.blit(label_font.render("Current life", True, (170, 170, 190)), (pad, y))
    y += 20
    if is_playing:
        elapsed, dmg_dealt, dodges, parries = current_life
        life_lines = [
            f"Survived: {elapsed:.1f}s",
            f"Damage dealt: {dmg_dealt:.1f}",
            f"Dodges: {dodges}    Perfect parries: {parries}",
        ]
    else:
        life_lines = [" (between lives)"]
    for line in life_lines:
        txt = small_font.render(line, True, (210, 210, 220))
        screen.blit(txt, (pad, y))
        y += txt.get_height() + 3
    y += 8

    # --- cumulative ability usage histogram ---
    screen.blit(label_font.render("Ability usage (all-time)", True, (170, 170, 190)), (pad, y))
    y += 20
    total_choices = max(1, sum(ability_counts))
    for i in range(4):
        bar_h = 16
        frac = ability_counts[i] / total_choices
        rect_bg = pygame.Rect(pad, y, inner_w, bar_h)
        pygame.draw.rect(screen, (35, 35, 48), rect_bg)
        pygame.draw.rect(screen, ABILITY_COLORS[i], pygame.Rect(pad, y, max(2, int(inner_w * frac)), bar_h))
        txt = small_font.render(f"{ABILITY_NAMES[i]} ({ability_counts[i]})", True, (235, 235, 235))
        screen.blit(txt, (pad + 4, y + 1))
        y += bar_h + 4
    y += 8

    # --- Watcher (Critic) panel ---
    screen.blit(label_font.render("Watcher (Critic)", True, (170, 170, 190)), (pad, y))
    y += 20
    if last_record is not None:
        watcher_lines = [
            f"Last life: {last_record['time_survived']:.1f}s survived",
            f" dmg {last_record['damage_dealt']:.0f}  dodges {last_record['dodges']}"
            f"  parries {last_record['parries']}",
            f" score {last_record['score']:.2f}  (best {watcher.best_score:.2f})",
            f" pain scale: {last_record['pain_scale']:.2f}"
            + ("  [MAX: stood still]" if last_record["stood_still"] else ""),
        ]
    else:
        watcher_lines = [" (no deaths recorded yet)"]
    for line in watcher_lines:
        txt = small_font.render(line, True, (210, 210, 220))
        screen.blit(txt, (pad, y))
        y += txt.get_height() + 3
    y += 8

    if len(watcher.history) >= 1:
        spark_h = 44
        spark_rect = pygame.Rect(pad, y, inner_w, spark_h)
        pygame.draw.rect(screen, (10, 10, 16), spark_rect)
        pygame.draw.rect(screen, (50, 50, 65), spark_rect, width=1)
        scores = list(watcher.history)
        n = len(scores)
        bar_w = max(1, spark_rect.w // max(n, 1))
        for i, rec in enumerate(scores):
            bh = max(1, int(rec["score"] * (spark_h - 4)))
            bx = spark_rect.x + i * bar_w
            by = spark_rect.bottom - bh
            color = (255, 90, 90) if rec["stood_still"] else (120, 220, 140)
            pygame.draw.rect(screen, color, pygame.Rect(bx, by, max(1, bar_w - 1), bh))
        y += spark_h + 6
        caption = small_font.render("score per life (red = stood still & died)", True, (140, 140, 155))
        screen.blit(caption, (pad, y))
        y += caption.get_height() + 12

    # --- Learning (trainable readout) panel ---
    # This is the part of the brain that actually learns via gradient
    # descent (REINFORCE), separate from the Watcher's pain/harmony
    # scrambling of the raw connectome. See FlyBrain.learn_from_life.
    screen.blit(label_font.render("Learning (readout)", True, (170, 170, 190)), (pad, y))
    y += 20
    if learning_stats is not None:
        sign = "+" if learning_stats["advantage"] >= 0 else ""
        learn_lines = [
            f"Policy updates: {total_updates}",
            f"Last reward: {learning_stats['reward']:.2f}"
            f"  (advantage {sign}{learning_stats['advantage']:.2f})",
            f"Reward baseline (avg): {learning_stats['baseline']:.2f}",
            f"Decisions in last life: {learning_stats['decisions']}",
        ]
    else:
        learn_lines = [
            f"Policy updates: {total_updates}",
            " (no completed life yet -- learns after",
            "  the first death or win)",
        ]
    for line in learn_lines:
        txt = small_font.render(line, True, (210, 210, 220))
        screen.blit(txt, (pad, y))
        y += txt.get_height() + 3
    y += 8

    if len(reward_history) >= 1:
        spark_h = 40
        spark_rect = pygame.Rect(pad, y, inner_w, spark_h)
        pygame.draw.rect(screen, (10, 10, 16), spark_rect)
        pygame.draw.rect(screen, (50, 50, 65), spark_rect, width=1)
        rewards = list(reward_history)
        n = len(rewards)
        bar_w = max(1, spark_rect.w // max(n, 1))
        for i, r in enumerate(rewards):
            bh = max(1, int(min(r, WIN_REWARD) / WIN_REWARD * (spark_h - 4)))
            bx = spark_rect.x + i * bar_w
            by = spark_rect.bottom - bh
            color = (120, 190, 255) if r >= WIN_REWARD else (200, 200, 90)
            pygame.draw.rect(screen, color, pygame.Rect(bx, by, max(1, bar_w - 1), bh))
        y += spark_h + 6
        caption = small_font.render("reward per life (blue = win)", True, (140, 140, 155))
        screen.blit(caption, (pad, y))


# ==============================================================================
# GAME LOOP
# ==============================================================================
def main():
    if not os.path.exists(CSV_PATH):
        print(f"[fatal] Could not find '{CSV_PATH}' next to main.py. "
              f"Place your FlyWire 'Connections (Filtered)' CSV (.csv or "
              f".csv.gz both work) there, or edit CSV_PATH at the top of "
              f"this file.")
        sys.exit(1)

    print("[brain] Building connectome brain -- this can take a few seconds "
          "on the first load...")
    brain = FlyBrain(CSV_PATH)

    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Fly Brain: Boss Fight")
    clock = pygame.time.Clock()
    big_font = pygame.font.SysFont("arial", 48, bold=True)
    sidebar_fonts = (
        pygame.font.SysFont("arial", 20, bold=True),   # title
        pygame.font.SysFont("arial", 15, italic=True),  # section labels
        pygame.font.SysFont("arial", 14),               # body text
    )

    boss_texture = load_image_safe(IMAGE_PATH, (220, 220))
    death_sound = load_sound_safe(SOUND_PATH)

    arena_w = SCREEN_W - ARENA_X
    boss = Boss(boss_texture, ARENA_X + arena_w * 0.68, SCREEN_H * 0.5)
    fly = Fly(ARENA_X + arena_w * 0.18, SCREEN_H * 0.5)

    state = {"attacking": 0, "defending": 0, "boss_hp": 1.0, "fly_hp": 1.0}

    def boss_state_provider():
        return (state["attacking"], state["defending"], state["boss_hp"], state["fly_hp"])

    brain_thread = FlyBrainThread(brain)
    brain_thread.start(boss_state_provider)

    watcher = Watcher()
    last_watcher_record = None
    learning_stats = None  # latest FlyBrain.learn_from_life() result, for the sidebar

    GAME = "playing"
    freeze_timer = 0.0
    last_ability_seen = -1
    attack_cooldown = 0.0
    parry_whiff_cooldown = 0.0  # rate-limits the Parry whiff penalty (see below) to
                                # roughly once per brain decision, not once per 0.3s
                                # re-trigger -- otherwise "hold Parry with nothing to
                                # parry" would rack up 4x the intended self-damage
    incoming_damage_timer = 0.0
    lives_lost = 0
    wins = 0

    # per-life telemetry the Watcher scores when this life ends in death
    life_elapsed = 0.0
    life_damage_dealt = 0.0
    life_dodges = 0
    life_parries = 0

    # for the sidebar's live/moving brain-activity chart
    last_seen_decision_count = 0
    logit_history = deque(maxlen=LOGIT_HISTORY_LEN)
    decision_timestamps = deque(maxlen=30)
    current_logits = None
    ability_counts = [0, 0, 0, 0]  # cumulative, across the whole session

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        state["boss_hp"] = boss.hp / boss.max_hp
        state["fly_hp"] = fly.hp / fly.max_hp
        state["attacking"] = 1 if boss.is_attacking else 0
        state["defending"] = 1 if boss.is_defending else 0

        ability_idx, logits, decision_count = brain_thread.latest()
        if decision_count != last_seen_decision_count:
            # A new decision landed (even if it picked the same ability as
            # last time) -- this is what makes the sidebar chart genuinely
            # "moving" rather than only updating when behavior changes.
            last_seen_decision_count = decision_count
            current_logits = logits.tolist()
            logit_history.append(current_logits)
            decision_timestamps.append(time.time())
            ability_counts[ability_idx] += 1

        if GAME == "playing":
            boss.update(dt)
            fly.update(dt)
            attack_cooldown = max(0.0, attack_cooldown - dt)
            parry_whiff_cooldown = max(0.0, parry_whiff_cooldown - dt)
            life_elapsed += dt

            # Anticipating the telegraph is what separates a perfect parry
            # from an ordinary reactive dodge -- see PARRY MECHANIC constants
            # and Boss.register_parry_attempt().
            if boss.state == "telegraph" and ability_idx == 2:
                boss.register_parry_attempt()

            if ability_idx != last_ability_seen or fly.action_timer <= 0:
                if attack_cooldown <= 0:
                    last_ability_seen = ability_idx
                    fly.trigger_ability(ability_idx)
                    attack_cooldown = 0.6

                    if ability_idx == 0:      # Light Attack
                        dmg = random.uniform(3, 7)
                        if boss.is_defending:
                            dmg *= BOSS_DEFEND_DAMAGE_REDUCTION
                        boss.hp = max(0, boss.hp - dmg)
                        life_damage_dealt += dmg
                        boss.on_hit()
                        fly.on_landed_hit()
                    elif ability_idx == 1:    # Heavy Attack
                        dmg = random.uniform(10, 18)
                        if boss.is_defending:
                            dmg *= BOSS_DEFEND_DAMAGE_REDUCTION
                        boss.hp = max(0, boss.hp - dmg)
                        life_damage_dealt += dmg
                        boss.on_hit()
                        fly.on_landed_hit()
                        incoming_damage_timer = 0.6  # riskier: more open next hit
                    elif ability_idx == 2:    # Parry
                        # Committing to Parry with nothing to actually parry
                        # (boss isn't telegraphing or mid-attack) is now a
                        # real mistake, not a free safe default -- it costs
                        # HP for being caught off-balance. A well-timed parry
                        # is resolved below, against the boss's attack frame.
                        # Rate-limited to ~once per decision (see
                        # parry_whiff_cooldown) so holding the same Parry
                        # decision doesn't get re-punished on every 0.3s
                        # animation re-trigger.
                        if boss.state not in ("telegraph", "attacking") and parry_whiff_cooldown <= 0:
                            whiff_dmg = random.uniform(PARRY_WHIFF_DAMAGE_MIN, PARRY_WHIFF_DAMAGE_MAX)
                            fly.take_damage(whiff_dmg)
                            parry_whiff_cooldown = DECISION_INTERVAL
                    elif ability_idx == 3:    # Heal
                        fly.hp = min(fly.max_hp, fly.hp + random.uniform(8, 14))

            # boss deals damage to fly on its attack frame -- resolved via
            # boss.hit_resolved rather than zeroing boss.timer, so the
            # "attacking" animation still plays out its full, visible
            # duration instead of collapsing back to idle within ~2 frames
            # (that timer-zeroing was the reason the boss looked static).
            if boss.state == "attacking" and not boss.hit_resolved:
                holding_parry = ability_idx == 2 and fly.action_timer > 0
                perfect_parry = holding_parry and boss.parry_window_hit
                if perfect_parry:
                    # Anticipated the telegraph -- full punish: no damage
                    # taken, a big counter hit, and the boss is staggered
                    # back to idle instead of getting to keep attacking.
                    counter_dmg = random.uniform(PARRY_COUNTER_DAMAGE_MIN, PARRY_COUNTER_DAMAGE_MAX)
                    boss.hp = max(0, boss.hp - counter_dmg)
                    life_damage_dealt += counter_dmg
                    boss.on_hit()
                    fly.on_landed_hit()
                    life_parries += 1
                    boss.state = "idle"
                    boss.timer = PARRY_STAGGER_TIME
                elif holding_parry:
                    # Reacted only once the hit was already live -- still
                    # works like the old Dodge (damage avoided), just no
                    # counter-damage bonus for not having anticipated it.
                    life_dodges += 1
                else:
                    dmg = random.uniform(BOSS_ATTACK_MIN, BOSS_ATTACK_MAX)
                    if incoming_damage_timer > 0:
                        dmg *= BOSS_PUNISH_MULTIPLIER
                    if boss.is_enraged:
                        dmg *= BOSS_ENRAGE_DAMAGE_MULT
                    fly.take_damage(dmg)
                boss.hit_resolved = True

            if fly.hp <= 0:
                GAME = "death_freeze"
                freeze_timer = 1.4
                if death_sound:
                    death_sound.play()

                # --- Watcher: score this attempt and scale the pain ---
                last_watcher_record = watcher.score_life(
                    life_elapsed, life_damage_dealt, life_dodges, life_parries, boss.max_hp
                )
                pain_intensity = BASE_PAIN_INTENSITY * last_watcher_record["pain_scale"]
                brain.apply_pain(intensity=pain_intensity)
                # --- genuine learning: REINFORCE update on the trainable
                # readout, using the Watcher's own score as the reward. This
                # is separate from (and in addition to) the pain scramble
                # above, which perturbs the underlying connectome instead.
                learning_stats = brain.learn_from_life(last_watcher_record["score"])
                print(
                    f"[watcher] life ended: survived {life_elapsed:.1f}s, "
                    f"dealt {life_damage_dealt:.1f} dmg, {life_dodges} dodges, "
                    f"{life_parries} perfect parries "
                    f"-> score {last_watcher_record['score']:.2f}, "
                    f"pain_scale {last_watcher_record['pain_scale']:.2f} "
                    f"(intensity {pain_intensity:.1f})"
                    + (" [MAX PAIN: stood still and died instantly]"
                       if last_watcher_record["stood_still"] else "")
                )
                if learning_stats:
                    print(
                        f"[learn] readout update #{learning_stats['updates']}: "
                        f"reward {learning_stats['reward']:.2f}, "
                        f"advantage {learning_stats['advantage']:+.2f}, "
                        f"baseline {learning_stats['baseline']:.2f}"
                    )
                lives_lost += 1
                life_elapsed = life_damage_dealt = 0.0
                life_dodges = life_parries = 0
            elif boss.hp <= 0:
                GAME = "win_freeze"
                freeze_timer = 2.0
                brain.apply_harmony()
                learning_stats = brain.learn_from_life(WIN_REWARD)
                if learning_stats:
                    print(
                        f"[learn] readout update #{learning_stats['updates']} (WIN): "
                        f"reward {learning_stats['reward']:.2f}, "
                        f"advantage {learning_stats['advantage']:+.2f}, "
                        f"baseline {learning_stats['baseline']:.2f}"
                    )
                wins += 1
                life_elapsed = life_damage_dealt = 0.0
                life_dodges = life_parries = 0

        elif GAME == "death_freeze":
            freeze_timer -= dt
            if freeze_timer <= 0:
                fly.reset()
                boss.reset()
                GAME = "playing"

        elif GAME == "win_freeze":
            freeze_timer -= dt
            if freeze_timer <= 0:
                fly.reset()
                boss.reset()
                GAME = "playing"

        # -- draw --
        screen.fill((18, 18, 28))
        boss.draw(screen)
        fly.draw(screen)

        decisions_per_sec = 0.0
        if len(decision_timestamps) >= 2:
            span = decision_timestamps[-1] - decision_timestamps[0]
            if span > 0:
                decisions_per_sec = (len(decision_timestamps) - 1) / span

        draw_sidebar(screen, sidebar_fonts, logit_history, current_logits,
                     decisions_per_sec, brain.locked, lives_lost, wins,
                     watcher, last_watcher_record, ability_counts,
                     (life_elapsed, life_damage_dealt, life_dodges, life_parries),
                     learning_stats, brain.reward_history, brain.total_updates,
                     GAME == "playing")

        arena_rect = pygame.Rect(ARENA_X, 0, SCREEN_W - ARENA_X, SCREEN_H)
        if GAME == "death_freeze":
            overlay = pygame.Surface(arena_rect.size, pygame.SRCALPHA)
            overlay.fill((80, 0, 0, 120))
            screen.blit(overlay, arena_rect.topleft)
            txt = big_font.render("THE FLY DIED", True, (255, 60, 60))
            screen.blit(txt, txt.get_rect(center=arena_rect.center))
        elif GAME == "win_freeze":
            overlay = pygame.Surface(arena_rect.size, pygame.SRCALPHA)
            overlay.fill((0, 60, 20, 120))
            screen.blit(overlay, arena_rect.topleft)
            txt = big_font.render("ETERNAL HARMONY", True, (120, 255, 170))
            screen.blit(txt, txt.get_rect(center=arena_rect.center))

        pygame.display.flip()

    brain_thread.stop()
    brain.shutdown()  # join any in-flight pain/harmony rebuild thread
    pygame.quit()


if __name__ == "__main__":
    main()
