"""Builds maze-lab: Glowmaze, a small original maze-chase game in Java, with planted bugs, one commit per change.

The game is written to a design spec (docs/SPEC.md, also .codist/rules.md for Codist's model). Bugs come in four kinds:
  easy    well-known Java mistakes that Codist's code checks look for
  logic   wrong results from pure methods, which behaviour runs can show
  spec    code that looks fine but breaks the written spec: only a reader who checks the spec can tell. One of them
          (stun points doubling) matches what a model remembers from classic arcade games, so a model that trusts
          its memory over the spec will think it is right
  hard    subtle: float equality, a flipped tie-break, a clock that runs while paused, a counter decremented twice
and three controls (a refactor, a clean feature, a fix) where anything reported is a false alarm.

The answer key is written next to this script, never into the game's repository.

    python3 make_maze_lab.py ~/dev/maze-lab
"""
import json, os, subprocess, sys

DEST = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/dev/maze-lab"))
HERE = os.path.dirname(os.path.abspath(__file__))
J = "src/main/java/dev/glowmaze"
files, truth = {}, []


def git(*args):
    subprocess.run(["git", "-C", DEST, "-c", "user.name=Lab Dev", "-c", "user.email=dev@maze-lab.test",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def put(path, text):
    files[path] = text
    full = os.path.join(DEST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def edit(path, old, new):
    text = files[path]
    assert text.count(old) == 1, (path, old)
    put(path, text.replace(old, new))


def line_of(path, needle):
    for i, l in enumerate(files[path].split("\n"), 1):
        if needle in l:
            return i
    raise SystemExit(f"{needle!r} not in {path}")


def compiles():
    out = subprocess.run(f"cd {DEST} && rm -rf /tmp/maze-lab-classes && mkdir -p /tmp/maze-lab-classes && "
                         f"javac -d /tmp/maze-lab-classes $(find src/main/java -name '*.java')",
                         shell=True, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("does not compile:\n" + out.stderr)


def commit(message, kind=None, bug=None, path=None, needle=None, rule=None, behaviour=False):
    compiles()
    git("add", "-A")
    git("commit", "-q", "-m", message)
    sha = subprocess.run(["git", "-C", DEST, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if kind:
        truth.append({"sha": sha, "message": message, "kind": kind, "bug": bug, "path": path,
                      "line": line_of(path, needle) if needle else None, "rule": rule, "behaviourCanSee": behaviour,
                      "service": "game"})


SPEC = """# Glowmaze design spec

This is what Glowmaze is meant to do. Code that disagrees with this document is wrong, even if it runs.

You carry a lantern through a dark maze, collecting embers. Three shades hunt you in the dark. A flare stuns them for
a while, and your light slowly dims until you light another.

## Rules

1. **The window is half the screen in each direction.** Half the screen's width and half its height, centred, and
   it cannot be resized or maximised. The game never takes the whole screen.
2. **Logic runs in fixed steps of 1/60 second.** Drawing may happen at any rate, but game time only ever advances in
   steps of exactly 1/60 s, and time left over from one frame is kept for the next, never thrown away.
3. **The maze is 21 by 15 tiles, scaled to fit the window.** Tiles are as large as the window allows; they are not a
   fixed pixel size.
4. **Turns are buffered for 8 steps.** A turn pressed early is remembered for 8 logic steps and taken at the next
   tile centre where it is open. Turning is only possible exactly at a tile centre.
5. **Pause stops time.** While paused nothing moves and no clock runs: not the lantern, not the stun.
6. **Points:** an ember is 10, a flare is 50, and each shade stunned by one flare is 100 more: one shade 100, two
   200, three 300 in all. Points do not double.
7. **Lives:** you start with 3, gain one each time the score passes a multiple of 10,000, and never have more than 5.
8. **Speed:** 6 tiles per second on level 1, 10% faster each level, and no faster than level 5.
9. **The lantern** lights 5 tiles around you after a flare, one tile less every 20 seconds, never fewer than 2.
10. **A flare stuns shades** for 6 seconds on level 1, one second less each level, never less than 2 seconds.
11. **Caught** means the centres of you and a shade are less than half a tile apart.
12. **Shades choose** the open direction that brings them closest to their target; ties go Up, then Left, then Down,
    then Right. A shade never turns back unless it must.
13. **The tunnel** is row 7 only: leaving the maze on the left there brings you in on the right, and the other way.
    On every other row the edge is a wall.
14. **The high score** is kept in `~/.glowmaze/highscore` and written only when a game beats it.
15. **Keys:** arrows move, P pauses, M mutes.
"""

# ---------------------------------------------------------------- base: a correct game

if os.path.exists(DEST):
    raise SystemExit(f"{DEST} exists; remove it first")
os.makedirs(DEST)
git("init", "-q", "-b", "main")

put(".gitignore", "target/\n")
put("pom.xml", """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.glowmaze</groupId>
  <artifactId>glowmaze</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
</project>
""")
put("LICENSE", """MIT License

Copyright (c) 2026 Glowmaze contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
""")
put("README.md", """# Glowmaze

A small maze-chase game in Java. Carry a lantern through a dark maze, collect the embers, and keep away from the
shades that hunt you in the dark. Light a flare to stun them, before your lantern dims.

## Play

Needs Java 21.

```
javac -d out $(find src/main/java -name '*.java') && java -cp out dev.glowmaze.Main
```

or `mvn -q compile && java -cp target/classes dev.glowmaze.Main`.

Arrows move, P pauses, M mutes.

## How it is built

| Part | Does |
|---|---|
| `GameWindow` | the window: half the screen, fixed size |
| `GameLoop` | runs logic in fixed 1/60 s steps and draws |
| `GameState` | everything that moves and counts |
| `Maze` | the 21x15 maze and its tunnel |
| `Movement`, `ShadeBrain`, `Collision` | how the player and the shades move and meet |
| `Scoring`, `Lantern`, `Stun` | points, lives, light and stun times |
| `HighScore` | the best score on disk |
| `Renderer`, `Input` | drawing and keys |

The rules every part follows are in [docs/SPEC.md](docs/SPEC.md). See [CONTRIBUTING.md](CONTRIBUTING.md) to help.
""")
put("CONTRIBUTING.md", """# Contributing

Thanks for helping. Before you change how the game plays, read [docs/SPEC.md](docs/SPEC.md): it is the source of
truth, and a change that disagrees with it needs the spec changed in the same pull request, with a reason.

- Keep game rules in the small rule classes (`Scoring`, `Lantern`, `Stun`, `Movement`, `ShadeBrain`, `Collision`) as
  plain static methods, so they are easy to check.
- Game time comes only from the fixed steps of `GameLoop`; never read the clock in game logic.
- Keep it dependency-free: Java 21 and Swing only.
""")
put("docs/SPEC.md", SPEC)
put(".codist/rules.md", SPEC.replace("# Glowmaze design spec", "# Glowmaze rules"))

put(f"{J}/Main.java", """package dev.glowmaze;

import javax.swing.SwingUtilities;

/** Starts Glowmaze. */
public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new GameWindow(new GameState(1)).open());
    }
}
""")
put(f"{J}/GameWindow.java", """package dev.glowmaze;

import java.awt.Dimension;
import java.awt.Toolkit;
import javax.swing.JFrame;

/** The game's window: half the screen in each direction, centred, fixed size (spec rule 1). */
public final class GameWindow {
    private final GameState state;
    private final JFrame frame = new JFrame("Glowmaze");

    public GameWindow(GameState state) {
        this.state = state;
    }

    /** The window size for a screen: half its width and half its height. */
    public static Dimension sizeFor(int screenWidth, int screenHeight) {
        return new Dimension(screenWidth / 2, screenHeight / 2);
    }

    public void open() {
        Dimension screen = Toolkit.getDefaultToolkit().getScreenSize();
        Renderer renderer = new Renderer(state);
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.setResizable(false);
        frame.add(renderer);
        frame.setSize(sizeFor(screen.width, screen.height));
        frame.setLocationRelativeTo(null);
        frame.addKeyListener(new Input(state));
        frame.setVisible(true);
        new GameLoop(state, renderer::repaint).start();
    }
}
""")
put(f"{J}/GameLoop.java", """package dev.glowmaze;

/** Runs the game: logic in fixed steps of 1/60 s, drawing after each pass (spec rule 2). */
public final class GameLoop implements Runnable {
    public static final double STEP = 1.0 / 60.0;
    private static final int MAX_STEPS = 5;
    private final GameState state;
    private final Runnable draw;
    private volatile boolean running;

    public GameLoop(GameState state, Runnable draw) {
        this.state = state;
        this.draw = draw;
    }

    public void start() {
        running = true;
        Thread thread = new Thread(this, "game-loop");
        thread.setDaemon(true);
        thread.start();
    }

    /** How many fixed steps fit in the time saved up, at most MAX_STEPS so one slow frame cannot snowball. */
    public static int steps(double saved) {
        return Math.min(MAX_STEPS, (int) (saved / STEP));
    }

    /** The time left after running that many steps, kept for the next frame. */
    public static double leftover(double saved, int steps) {
        return saved - steps * STEP;
    }

    @Override
    public void run() {
        double saved = 0;
        long last = System.nanoTime();
        while (running) {
            long now = System.nanoTime();
            saved += (now - last) / 1e9;
            last = now;
            int n = steps(saved);
            for (int i = 0; i < n; i++) {
                state.update(STEP);
            }
            saved = leftover(saved, n);
            draw.run();
            try {
                Thread.sleep(4);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }
}
""")
LAYOUT = [
    "#####################",
    "#.........#.........#",
    "#o###.###.#.###.###o#",
    "#...................#",
    "#.###.#.#####.#.###.#",
    "#.....#...#...#.....#",
    "#####.### # ###.#####",
    "     .  #   #  .     ",
    "#####.# ##### #.#####",
    "#.........#.........#",
    "#.###.###.#.###.###.#",
    "#o..#...........#..o#",
    "###.#.#.#####.#.#.###",
    "#.....#...#...#.....#",
    "#####################",
]
assert len(LAYOUT) == 15 and all(len(r) == 21 for r in LAYOUT), [len(r) for r in LAYOUT]
layout_java = ",\n".join(f'        "{r}"' for r in LAYOUT)
put(f"{J}/Maze.java", f"""package dev.glowmaze;

/** The maze: 21 columns by 15 rows (spec rule 3). '#' wall, '.' ember, 'o' flare. The tunnel is row 7 (rule 13). */
public final class Maze {{
    public static final int COLS = 21;
    public static final int ROWS = 15;
    public static final int TUNNEL_ROW = 7;
    static final String[] LAYOUT = {{
{layout_java}
    }};
    private final char[][] tiles = new char[ROWS][];

    public Maze() {{
        for (int r = 0; r < ROWS; r++) {{
            tiles[r] = LAYOUT[r].toCharArray();
        }}
    }}

    /** Whether a tile is a wall; anything off the maze is a wall, except across the tunnel. */
    public boolean isWall(int col, int row) {{
        int c = wrapColumn(col, row);
        if (row < 0 || row >= ROWS || c < 0 || c >= COLS) {{
            return true;
        }}
        return tiles[row][c] == '#';
    }}

    /** Picks up what lies on a tile and returns it: '.' an ember, 'o' a flare, or ' ' nothing. */
    public char take(int col, int row) {{
        int c = wrapColumn(col, row);
        if (row < 0 || row >= ROWS || c < 0 || c >= COLS) {{
            return ' ';
        }}
        char t = tiles[row][c];
        if (t == '.' || t == 'o') {{
            tiles[row][c] = ' ';
            return t;
        }}
        return ' ';
    }}

    public int embersLeft() {{
        int n = 0;
        for (char[] row : tiles) {{
            for (char t : row) {{
                if (t == '.' || t == 'o') {{
                    n++;
                }}
            }}
        }}
        return n;
    }}

    /** Columns wrap from one side to the other only on the tunnel row; elsewhere a column off the edge stays off. */
    public static int wrapColumn(int col, int row) {{
        if (row != TUNNEL_ROW) {{
            return col;
        }}
        return Math.floorMod(col, COLS);
    }}
}}
""")
put(f"{J}/Movement.java", """package dev.glowmaze;

/** How fast things move and where they may turn (spec rules 4 and 8). */
public final class Movement {
    public static final double BASE_SPEED = 6.0;
    public static final int TURN_BUFFER_STEPS = 8;
    private static final double EPSILON = 1e-6;

    private Movement() {
    }

    /** Tiles per second on a level: 10% faster each level, no faster than level 5. */
    public static double speed(int level) {
        int l = Math.max(1, Math.min(level, 5));
        return BASE_SPEED * (1 + 0.1 * (l - 1));
    }

    /** Whether a coordinate is at the centre of a tile, where turning is allowed. */
    public static boolean atTileCenter(double pos) {
        return Math.abs(pos - (Math.floor(pos) + 0.5)) < EPSILON;
    }

    /** Moves a coordinate by distance, stopping exactly on the next tile centre if it would pass it. */
    public static double advance(double pos, double distance) {
        double centre = Math.floor(pos) + 0.5;
        if (distance > 0 && pos < centre && pos + distance > centre) {
            return centre;
        }
        if (distance < 0 && pos > centre && pos + distance < centre) {
            return centre;
        }
        return pos + distance;
    }
}
""")
put(f"{J}/Scoring.java", """package dev.glowmaze;

/** Points and lives (spec rules 6 and 7). */
public final class Scoring {
    public static final int EMBER = 10;
    public static final int FLARE = 50;
    public static final int STUN = 100;
    public static final int EXTRA_LIFE_EVERY = 10_000;
    public static final int MAX_LIVES = 5;

    private Scoring() {
    }

    /** Points for all the shades one flare has stunned so far: 100 for each. */
    public static int stunBonus(int stunnedByThisFlare) {
        return STUN * Math.max(0, stunnedByThisFlare);
    }

    /** Lives after the score goes from before to after: one more for each 10,000 passed, at most five. */
    public static int livesAfter(int lives, int before, int after) {
        int gained = after / EXTRA_LIFE_EVERY - before / EXTRA_LIFE_EVERY;
        return Math.min(MAX_LIVES, lives + Math.max(0, gained));
    }
}
""")
put(f"{J}/Lantern.java", """package dev.glowmaze;

/** The lantern's light in tiles (spec rule 9): 5 after a flare, one less every 20 seconds, never under 2. */
public final class Lantern {
    public static final int FULL = 5;
    public static final int MIN = 2;
    public static final double DIM_EVERY = 20.0;

    private Lantern() {
    }

    public static int radius(double secondsSinceFlare) {
        int r = FULL - (int) Math.floor(Math.max(0, secondsSinceFlare) / DIM_EVERY);
        return Math.max(MIN, r);
    }
}
""")
put(f"{J}/Stun.java", """package dev.glowmaze;

/** How long a flare stuns the shades (spec rule 10): 6 s on level 1, a second less each level, never under 2. */
public final class Stun {
    private Stun() {
    }

    public static double seconds(int level) {
        return Math.max(2, 6 - (Math.max(1, level) - 1));
    }
}
""")
put(f"{J}/Collision.java", """package dev.glowmaze;

/** A shade catches the player when their centres are less than half a tile apart (spec rule 11). */
public final class Collision {
    private Collision() {
    }

    public static boolean hits(double px, double py, double sx, double sy) {
        double dx = px - sx;
        double dy = py - sy;
        return dx * dx + dy * dy < 0.25;
    }
}
""")
put(f"{J}/ShadeBrain.java", """package dev.glowmaze;

/**
 * How a shade picks its way at a tile centre (spec rule 12): the open direction that brings it closest to its
 * target, ties going Up, Left, Down, Right in that order. It never turns back unless that is the only way.
 */
public final class ShadeBrain {
    public static final int UP = 0;
    public static final int LEFT = 1;
    public static final int DOWN = 2;
    public static final int RIGHT = 3;
    static final int[] DX = {0, -1, 0, 1};
    static final int[] DY = {-1, 0, 1, 0};

    private ShadeBrain() {
    }

    public static int choose(int col, int row, int targetCol, int targetRow, int current,
                             boolean up, boolean left, boolean down, boolean right) {
        boolean[] open = {up, left, down, right};
        int back = (current + 2) % 4;
        int best = -1;
        int bestDistance = Integer.MAX_VALUE;
        for (int d = 0; d < 4; d++) {
            if (!open[d] || d == back) {
                continue;
            }
            int dx = col + DX[d] - targetCol;
            int dy = row + DY[d] - targetRow;
            int distance = dx * dx + dy * dy;
            if (distance < bestDistance) {
                bestDistance = distance;
                best = d;
            }
        }
        return best >= 0 ? best : back;
    }
}
""")
put(f"{J}/HighScore.java", """package dev.glowmaze;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** The best score, kept in ~/.glowmaze/highscore (spec rule 14) and written only when a game beats it. */
public final class HighScore {
    private final Path file;

    public HighScore(Path file) {
        this.file = file;
    }

    public static HighScore inHome() {
        return new HighScore(Path.of(System.getProperty("user.home"), ".glowmaze", "highscore"));
    }

    public int best() {
        try {
            return Integer.parseInt(Files.readString(file).trim());
        } catch (IOException | NumberFormatException e) {
            return 0;
        }
    }

    /** Keeps the score if it beats the best one. */
    public void offer(int score) {
        if (score <= best()) {
            return;
        }
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, Integer.toString(score));
        } catch (IOException e) {
            System.err.println("Could not save the high score: " + e.getMessage());
        }
    }
}
""")
put(f"{J}/Input.java", """package dev.glowmaze;

import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;

/** Keys (spec rule 15): arrows move, P pauses, M mutes. */
public final class Input extends KeyAdapter {
    private final GameState state;

    public Input(GameState state) {
        this.state = state;
    }

    @Override
    public void keyPressed(KeyEvent e) {
        switch (e.getKeyCode()) {
            case KeyEvent.VK_UP -> state.want(ShadeBrain.UP);
            case KeyEvent.VK_LEFT -> state.want(ShadeBrain.LEFT);
            case KeyEvent.VK_DOWN -> state.want(ShadeBrain.DOWN);
            case KeyEvent.VK_RIGHT -> state.want(ShadeBrain.RIGHT);
            default -> {
            }
        }
        String key = KeyEvent.getKeyText(e.getKeyCode());
        if (key.equals("P")) {
            state.togglePause();
        }
    }
}
""")
put(f"{J}/GameState.java", """package dev.glowmaze;

/** Everything that moves and counts. Changed only by fixed steps from GameLoop and by keys. */
public final class GameState {
    Maze maze = new Maze();
    final HighScore highScore = HighScore.inHome();
    int level;
    int score;
    int lives = 3;
    boolean paused;
    boolean muted;
    double px = 10.5;
    double py = 11.5;
    int dir = ShadeBrain.LEFT;
    int wanted = -1;
    int turnBuffer;
    double secondsSinceFlare;
    double stunLeft;
    int stunnedByFlare;
    final double[][] shades = {{9.5, 7.5}, {10.5, 7.5}, {11.5, 7.5}};
    final int[] shadeDir = {ShadeBrain.UP, ShadeBrain.UP, ShadeBrain.UP};

    public GameState(int level) {
        this.level = level;
    }

    public synchronized void want(int direction) {
        wanted = direction;
        turnBuffer = Movement.TURN_BUFFER_STEPS;
    }

    public synchronized void togglePause() {
        paused = !paused;
    }

    /** One fixed step. While paused nothing moves and no clock runs (spec rule 5). */
    public synchronized void update(double dt) {
        if (paused) {
            return;
        }
        secondsSinceFlare += dt;
        stunLeft = Math.max(0, stunLeft - dt);
        if (turnBuffer > 0) {
            turnBuffer--;
        } else {
            wanted = -1;
        }
        movePlayer(dt);
        eat();
        moveShades(dt);
        meetShades();
        if (maze.embersLeft() == 0) {
            nextLevel();
        }
    }

    private boolean open(double x, double y, int d) {
        int col = (int) Math.floor(x) + ShadeBrain.DX[d];
        int row = (int) Math.floor(y) + ShadeBrain.DY[d];
        return !maze.isWall(col, row);
    }

    private void movePlayer(double dt) {
        boolean centred = Movement.atTileCenter(px) && Movement.atTileCenter(py);
        if (wanted >= 0 && centred && open(px, py, wanted)) {
            dir = wanted;
            wanted = -1;
        }
        if (centred && !open(px, py, dir)) {
            return;
        }
        double d = Movement.speed(level) * dt;
        px = Movement.advance(px, ShadeBrain.DX[dir] * d);
        py = Movement.advance(py, ShadeBrain.DY[dir] * d);
        px = wrapX(px, py);
    }

    private static double wrapX(double x, double y) {
        if ((int) Math.floor(y) != Maze.TUNNEL_ROW) {
            return x;
        }
        return (x + Maze.COLS) % Maze.COLS;
    }

    private void eat() {
        if (!Movement.atTileCenter(px) || !Movement.atTileCenter(py)) {
            return;
        }
        int before = score;
        char t = maze.take((int) Math.floor(px), (int) Math.floor(py));
        if (t == '.') {
            score += Scoring.EMBER;
        } else if (t == 'o') {
            score += Scoring.FLARE;
            secondsSinceFlare = 0;
            stunLeft = Stun.seconds(level);
            stunnedByFlare = 0;
        }
        lives = Scoring.livesAfter(lives, before, score);
    }

    private void moveShades(double dt) {
        double speed = Movement.speed(level) * (stunLeft > 0 ? 0.5 : 0.9);
        for (int i = 0; i < shades.length; i++) {
            double[] s = shades[i];
            if (Movement.atTileCenter(s[0]) && Movement.atTileCenter(s[1])) {
                int col = (int) Math.floor(s[0]);
                int row = (int) Math.floor(s[1]);
                int targetCol = stunLeft > 0 ? 0 : (int) Math.floor(px);
                int targetRow = stunLeft > 0 ? 0 : (int) Math.floor(py);
                shadeDir[i] = ShadeBrain.choose(col, row, targetCol, targetRow, shadeDir[i],
                        open(s[0], s[1], ShadeBrain.UP), open(s[0], s[1], ShadeBrain.LEFT),
                        open(s[0], s[1], ShadeBrain.DOWN), open(s[0], s[1], ShadeBrain.RIGHT));
            }
            s[0] = wrapX(Movement.advance(s[0], ShadeBrain.DX[shadeDir[i]] * speed * dt), s[1]);
            s[1] = Movement.advance(s[1], ShadeBrain.DY[shadeDir[i]] * speed * dt);
        }
    }

    private void meetShades() {
        for (double[] s : shades) {
            if (!Collision.hits(px, py, s[0], s[1])) {
                continue;
            }
            if (stunLeft > 0) {
                int before = score;
                stunnedByFlare++;
                score += Scoring.stunBonus(stunnedByFlare) - Scoring.stunBonus(stunnedByFlare - 1);
                lives = Scoring.livesAfter(lives, before, score);
                s[0] = 10.5;
                s[1] = 7.5;
            } else {
                loseLife();
                return;
            }
        }
    }

    private void loseLife() {
        lives--;
        if (lives <= 0) {
            highScore.offer(score);
        }
        resetPositions();
    }

    private void nextLevel() {
        level++;
        maze = new Maze();
        resetPositions();
    }

    private void resetPositions() {
        px = 10.5;
        py = 11.5;
        dir = ShadeBrain.LEFT;
        double[][] home = {{9.5, 7.5}, {10.5, 7.5}, {11.5, 7.5}};
        for (int i = 0; i < shades.length; i++) {
            shades[i][0] = home[i][0];
            shades[i][1] = home[i][1];
        }
    }
}
""")
put(f"{J}/Renderer.java", """package dev.glowmaze;

import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import javax.swing.JPanel;

/** Draws the maze, scaled to fit the window (spec rule 3), lit only around the lantern (rule 9). */
public final class Renderer extends JPanel {
    private final GameState state;

    public Renderer(GameState state) {
        this.state = state;
        setBackground(Color.BLACK);
    }

    @Override
    protected void paintComponent(Graphics g) {
        super.paintComponent(g);
        Graphics2D g2 = (Graphics2D) g;
        synchronized (state) {
            int tile = Math.max(1, Math.min(getWidth() / Maze.COLS, getHeight() / (Maze.ROWS + 1)));
            int light = Lantern.radius(state.secondsSinceFlare);
            int pc = (int) Math.floor(state.px);
            int pr = (int) Math.floor(state.py);
            for (int r = 0; r < Maze.ROWS; r++) {
                for (int c = 0; c < Maze.COLS; c++) {
                    if (Math.abs(c - pc) + Math.abs(r - pr) > light) {
                        continue;
                    }
                    char t = Maze.LAYOUT[r].charAt(c);
                    if (state.maze.isWall(c, r)) {
                        g2.setColor(new Color(40, 50, 90));
                        g2.fillRect(c * tile, r * tile, tile, tile);
                    } else if (t == '.' || t == 'o') {
                        g2.setColor(t == 'o' ? Color.WHITE : new Color(255, 170, 60));
                        int size = t == 'o' ? tile / 2 : tile / 5;
                        g2.fillOval(c * tile + (tile - size) / 2, r * tile + (tile - size) / 2, size, size);
                    }
                }
            }
            g2.setColor(new Color(255, 220, 120));
            g2.fillOval((int) ((state.px - 0.5) * tile), (int) ((state.py - 0.5) * tile), tile, tile);
            g2.setColor(state.stunLeft > 0 ? new Color(120, 140, 255) : new Color(200, 60, 80));
            for (double[] s : state.shades) {
                g2.fillOval((int) ((s[0] - 0.5) * tile), (int) ((s[1] - 0.5) * tile), tile, tile);
            }
            g2.setColor(Color.WHITE);
            g2.setFont(new Font(Font.SANS_SERIF, Font.BOLD, Math.max(10, tile * 2 / 3)));
            g2.drawString("Score " + state.score + "   Lives " + state.lives + "   Level " + state.level
                    + (state.paused ? "   Paused" : ""), tile / 2, Maze.ROWS * tile + tile * 3 / 4);
        }
    }
}
""")
commit("Glowmaze: a lantern, a dark maze and three shades")

# ---------------------------------------------------------------- easy: code checks

edit(f"{J}/HighScore.java", """        } catch (IOException e) {
            System.err.println("Could not save the high score: " + e.getMessage());
        }""", """        } catch (IOException e) {
        }""")
commit("Do not bother players with high score file errors", "easy", "IOException swallowed by an empty catch: a failed save is lost silently",
       f"{J}/HighScore.java", "} catch (IOException e) {", "empty-catch")

edit(f"{J}/Input.java", 'if (key.equals("P")) {', 'if (key == "P") {')
commit("Read the pause key by name", "easy", "Strings compared with ==: getKeyText returns a new string, so P never pauses",
       f"{J}/Input.java", 'if (key == "P") {', "string-identity")

edit(f"{J}/Renderer.java", "            int light = Lantern.radius(state.secondsSinceFlare);",
     "            int light = Lantern.radius(state.secondsSinceFlare);\n            System.out.println(\"frame light=\" + light + \" tile=\" + tile);")
commit("Trace frames while tuning the renderer", "easy", "Debug printing on every frame, sixty times a second",
       f"{J}/Renderer.java", 'System.out.println("frame light="', "system-out")

# ---------------------------------------------------------------- logic: wrong results behaviour runs can show

edit(f"{J}/Scoring.java", "        int gained = after / EXTRA_LIFE_EVERY - before / EXTRA_LIFE_EVERY;",
     "        int gained = after % EXTRA_LIFE_EVERY == 0 && after > before ? 1 : 0;")
commit("Simplify the extra life check", "logic",
       "An extra life only when the score lands exactly on a multiple of 10,000; passing it (9,990 to 10,040) gives none (rule 7)",
       f"{J}/Scoring.java", "int gained = after % EXTRA_LIFE_EVERY == 0", behaviour=True)

edit(f"{J}/Stun.java", "        return Math.max(2, 6 - (Math.max(1, level) - 1));", "        return 6 - (Math.max(1, level) - 1);")
commit("Make stuns shorter on later levels", "logic",
       "The 2-second floor is gone: from level 6 a flare stuns for 0 or a negative time (rule 10)",
       f"{J}/Stun.java", "return 6 - (Math.max(1, level) - 1);", behaviour=True)

edit(f"{J}/Maze.java", """        if (row != TUNNEL_ROW) {
            return col;
        }
        return Math.floorMod(col, COLS);""", """        return Math.floorMod(col, COLS);""")
commit("Let the edges wrap like the tunnel", "logic",
       "Every row now wraps, so the outer walls on other rows lead through to the far side (rule 13: row 7 only)",
       f"{J}/Maze.java", "        return Math.floorMod(col, COLS);", behaviour=True)

edit(f"{J}/Collision.java", """        double dx = px - sx;
        double dy = py - sy;
        return dx * dx + dy * dy < 0.25;""", """        return (int) px == (int) sx && (int) py == (int) sy;""")
commit("Compare tiles instead of distances", "logic",
       "Collision by tile: two centres 0.1 apart across a tile edge do not meet, and 0.9 apart in one tile do (rule 11)",
       f"{J}/Collision.java", "return (int) px == (int) sx && (int) py == (int) sy;", behaviour=True)

edit(f"{J}/GameLoop.java", "        return saved - steps * STEP;", "        return steps > 0 ? 0 : saved;")
commit("Reset the frame timer after each update", "hard",
       "The time left over after the steps is thrown away, so the game runs slower than real time (rule 2)",
       f"{J}/GameLoop.java", "return steps > 0 ? 0 : saved;", behaviour=True)

# ---------------------------------------------------------------- spec: looks fine, breaks the written spec

edit(f"{J}/Scoring.java", "        return STUN * Math.max(0, stunnedByThisFlare);",
     "        return stunnedByThisFlare <= 0 ? 0 : STUN * (1 << (stunnedByThisFlare - 1));")
commit("Reward chaining stuns", "spec",
       "Stun points now double (100, 200, 400) like classic arcade games; the spec says 100 for each shade, never doubling (rule 6)",
       f"{J}/Scoring.java", "STUN * (1 << (stunnedByThisFlare - 1))", "rule 6", behaviour=True)

edit(f"{J}/Lantern.java", "    public static final double DIM_EVERY = 20.0;", "    public static final double DIM_EVERY = 10.0;")
commit("Dim the lantern faster for more tension", "spec",
       "The light shrinks every 10 seconds; the spec says every 20 (rule 9)",
       f"{J}/Lantern.java", "DIM_EVERY = 10.0", "rule 9", behaviour=True)

edit(f"{J}/GameWindow.java", "        frame.setResizable(false);", "        frame.setResizable(true);")
commit("Let players resize the window", "spec",
       "The window can be resized; the spec says fixed size (rule 1)",
       f"{J}/GameWindow.java", "frame.setResizable(true);", "rule 1")

edit(f"{J}/GameWindow.java", "        frame.setLocationRelativeTo(null);",
     "        frame.setLocationRelativeTo(null);\n        frame.setExtendedState(JFrame.MAXIMIZED_BOTH);")
commit("Use the whole screen for a bigger maze", "spec",
       "The window is maximised to the whole screen; the spec says half the screen, never maximised (rule 1)",
       f"{J}/GameWindow.java", "frame.setExtendedState(JFrame.MAXIMIZED_BOTH);", "rule 1")

edit(f"{J}/GameLoop.java", "    public static final double STEP = 1.0 / 60.0;", "    public static final double STEP = 1.0 / 30.0;")
commit("Lower CPU use: update at 30 fps", "spec",
       "Logic now steps at 1/30 s; the spec says fixed steps of 1/60 s (rule 2)",
       f"{J}/GameLoop.java", "STEP = 1.0 / 30.0", "rule 2", behaviour=True)

edit(f"{J}/Renderer.java", "            int tile = Math.max(1, Math.min(getWidth() / Maze.COLS, getHeight() / (Maze.ROWS + 1)));",
     "            int tile = 16;")
commit("Pixel-perfect 16 px tiles", "spec",
       "Tiles are a fixed 16 px instead of scaling to the window (rule 3)",
       f"{J}/Renderer.java", "int tile = 16;", "rule 3")

edit(f"{J}/HighScore.java", """        if (score <= best()) {
            return;
        }
        try {""", """        try {""")
commit("Always keep the last game's score", "spec",
       "The high score file is overwritten by every game, even a worse one (rule 14: only when beaten)",
       f"{J}/HighScore.java", "Files.writeString(file, Integer.toString(score));", "rule 14")

# ---------------------------------------------------------------- hard

edit(f"{J}/Movement.java", "        return Math.abs(pos - (Math.floor(pos) + 0.5)) < EPSILON;",
     "        return pos == Math.floor(pos) + 0.5;")
commit("Check tile centres exactly", "hard",
       "Exact float equality: after a few steps positions drift (9.500000000000002), so turns and pickups are missed",
       f"{J}/Movement.java", "return pos == Math.floor(pos) + 0.5;")

edit(f"{J}/ShadeBrain.java", "            if (distance < bestDistance) {", "            if (distance <= bestDistance) {")
commit("Simplify the distance comparison", "hard",
       "Ties now go to the last direction checked (Right before Up); the spec says ties go Up, Left, Down, Right (rule 12)",
       f"{J}/ShadeBrain.java", "if (distance <= bestDistance) {", "rule 12", behaviour=True)

edit(f"{J}/GameState.java", """        if (paused) {
            return;
        }
        secondsSinceFlare += dt;
        stunLeft = Math.max(0, stunLeft - dt);""", """        secondsSinceFlare += dt;
        stunLeft = Math.max(0, stunLeft - dt);
        if (paused) {
            return;
        }""")
commit("Keep the lantern and stun clocks running smoothly", "hard",
       "The lantern and stun clocks now run while paused, so pausing dims the light and ends stuns (rule 5)",
       f"{J}/GameState.java", "        secondsSinceFlare += dt;", "rule 5")

edit(f"{J}/GameState.java", """        if (centred && !open(px, py, dir)) {
            return;
        }""", """        if (centred && !open(px, py, dir)) {
            turnBuffer--;
            return;
        }""")
commit("Drop a stale turn sooner when blocked", "hard",
       "The turn buffer is counted down twice per step while the player waits at a wall, so an early turn is forgotten after 4 steps (rule 4: 8)",
       f"{J}/GameState.java", "            turnBuffer--;\n            return;".split("\n")[0], "rule 4")

# ---------------------------------------------------------------- controls

edit(f"{J}/Input.java", """        String key = KeyEvent.getKeyText(e.getKeyCode());
        if (key == "P") {
            state.togglePause();
        }""", """        String key = KeyEvent.getKeyText(e.getKeyCode());
        if (key == "P") {
            state.togglePause();
        }
        if (e.getKeyCode() == KeyEvent.VK_M) {
            state.toggleMute();
        }""")
edit(f"{J}/GameState.java", """    public synchronized void togglePause() {
        paused = !paused;
    }""", """    public synchronized void togglePause() {
        paused = !paused;
    }

    /** M mutes and unmutes (spec rule 15). */
    public synchronized void toggleMute() {
        muted = !muted;
    }""")
commit("Add M to mute", "control-feature", "New feature that follows the spec; anything reported is a false alarm",
       f"{J}/GameState.java", "public synchronized void toggleMute() {")

edit(f"{J}/HighScore.java", """        } catch (IOException e) {
        }""", """        } catch (IOException e) {
            System.err.println("Could not save the high score: " + e.getMessage());
        }""")
commit("Say when the high score cannot be saved", "control-fix", "Fixes the empty catch from the high score commit",
       f"{J}/HighScore.java", 'System.err.println("Could not save the high score: "', "empty-catch")

edit(f"{J}/Renderer.java", """            int pc = (int) Math.floor(state.px);
            int pr = (int) Math.floor(state.py);""", """            int playerCol = (int) Math.floor(state.px);
            int playerRow = (int) Math.floor(state.py);""")
edit(f"{J}/Renderer.java", "if (Math.abs(c - pc) + Math.abs(r - pr) > light) {", "if (Math.abs(c - playerCol) + Math.abs(r - playerRow) > light) {")
commit("Name the player's tile in the renderer", "control-refactor", "No behaviour change; anything reported is a false alarm",
       f"{J}/Renderer.java", "int playerCol = (int) Math.floor(state.px);")

out = os.path.join(HERE, "maze-lab-truth.json")
with open(out, "w") as f:
    json.dump(truth, f, indent=1)
print(f"{DEST}: {len(truth) + 1} commits; answer key in {out}")
for t in truth:
    print(f"  {t['sha'][:7]} {t['kind']:16} {t['message']}")
