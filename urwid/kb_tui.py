# app_oo_kb.py
# pip install urwid
import os, sqlite3, urwid
from typing import List, Dict, Optional, Tuple

DB_PATH = "kb.db"

# ---------------------------
# Data layer (Repo)
# ---------------------------
class Repo:
    def __init__(self, path: str):
        self.path = path
        self._ensure_db()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _ensure_db(self):
        new = not os.path.exists(self.path)
        with self._conn() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS articles (
              id TEXT PRIMARY KEY,
              title   TEXT NOT NULL,
              summary TEXT,
              content TEXT NOT NULL
            );

            /* Navigation tree: unlimited depth via parent_id */
            CREATE TABLE IF NOT EXISTS nodes (
              id TEXT PRIMARY KEY,
              parent_id TEXT,
              label TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('menu','article','list')),
              target_id TEXT,
              query TEXT,
              sort_order INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
            """)

            # Seed minimal content if empty
            cur = c.execute("SELECT COUNT(*) FROM articles")
            art_count = cur.fetchone()[0]
            cur = c.execute("SELECT COUNT(*) FROM nodes")
            node_count = cur.fetchone()[0]

            if art_count == 0:
                c.executemany(
                    "INSERT INTO articles (id,title,summary,content) VALUES (?,?,?,?)",
                    [
                        ("a1","Getting Started","Intro & onboarding",
                         "Welcome to the Knowledge Base.\n\nThis is a seed article."),
                        ("a2","Networking FAQ","Common network issues",
                         "Ping/ICMP, SSH, security groups, VPC routing."),
                        ("a3","Linux Cheatsheet","Commands & tips",
                         "ls, grep, awk, sed, systemd basics."),
                        ("a4","Deploy Guide","CI/CD and releases",
                         "Tagging, pipelines, rollouts, rollback playbook."),
                    ]
                )
            if node_count == 0:
                c.executemany(
                    "INSERT INTO nodes (id,parent_id,label,kind,target_id,query,sort_order) VALUES (?,?,?,?,?,?,?)",
                    [
                        ("root", None, "Home", "menu", None, None, 0),

                        # direct links to articles
                        ("n1","root","Getting Started","article","a1",None,10),
                        ("n2","root","Guides","menu",None,None,20),
                        ("n2_1","n2","Deploy Guide","article","a4",None,0),

                        # dynamic list (query = show all)
                        ("n3","root","All Articles","list",None,"*",30),

                        # another nested menu level
                        ("n4","root","Reference","menu",None,None,40),
                        ("n4_1","n4","Linux Cheatsheet","article","a3",None,0),
                        ("n4_2","n4","Networking FAQ","article","a2",None,1),
                    ]
                )

    # ---- Navigation tree ----
    def get_children(self, parent_id: Optional[str]) -> List[Dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id,parent_id,label,kind,target_id,query "
                "FROM nodes WHERE parent_id IS ? ORDER BY sort_order, label",
                (parent_id,))
            rows = cur.fetchall()
        return [dict(zip(["id","parent_id","label","kind","target_id","query"], r)) for r in rows]

    def get_node(self, node_id: str) -> Dict:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id,parent_id,label,kind,target_id,query FROM nodes WHERE id=?",
                (node_id,))
            row = cur.fetchone()
        if not row:
            raise KeyError(node_id)
        return dict(zip(["id","parent_id","label","kind","target_id","query"], row))

    def get_article(self, article_id: str) -> Dict:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id,title,summary,content FROM articles WHERE id=?",
                (article_id,))
            row = cur.fetchone()
        if not row:
            raise KeyError(article_id)
        return dict(zip(["id","title","summary","content"], row))

    def search_articles(self, query: str) -> List[Dict]:
        q = (query or "").strip()
        with self._conn() as c:
            if q == "*" or q == "":
                cur = c.execute(
                    "SELECT id,title,summary,content FROM articles ORDER BY title"
                )
            else:
                like = f"%{q}%"
                cur = c.execute(
                    "SELECT id,title,summary,content FROM articles "
                    "WHERE title LIKE ? OR summary LIKE ? OR content LIKE ? "
                    "ORDER BY title", (like, like, like))
            rows = cur.fetchall()
        return [dict(zip(["id","title","summary","content"], r)) for r in rows]

# ---------------------------
# UI theme
# ---------------------------
PALETTE = [
    ("bg", "dark green", "black"),
    ("dim", "dark gray", "black"),
    ("title", "yellow", "black", "bold"),
    ("accent", "light green", "black", "bold"),
    ("list_focus", "black", "yellow"),
    ("warn", "yellow", "black"),
]

# ---------------------------
# Router & View base
# ---------------------------
class View:
    title: str = ""

    def __init__(self, app: "App"):
        self.app = app

    def widget(self) -> urwid.Widget:  # must return a Box widget
        raise NotImplementedError

    def handle_key(self, key: str) -> bool:
        """Return True if handled."""
        return False

class Router:
    def __init__(self, app: "App"):
        self.app = app
        self.stack: List[View] = []
        self.placeholder = urwid.WidgetPlaceholder(urwid.SolidFill(" "))

    def push(self, view: View):
        self.stack.append(view)
        self.placeholder.original_widget = view.widget()
        self.app.set_header(view.title)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()
            v = self.stack[-1]
            self.placeholder.original_widget = v.widget()
            self.app.set_header(v.title)

    def top(self) -> View:
        return self.stack[-1]

# ---------------------------
# Concrete Views
# ---------------------------
class MenuView(View):
    def __init__(self, app: "App", node_id: Optional[str], label: str = "Menu"):
        super().__init__(app)
        self.node_id = node_id
        self.title = f" KB • {label} "
        self.walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.walker)
        self._load_items()

    def _load_items(self):
        children = self.app.repo.get_children(self.node_id)
        self.walker.clear()
        for n in children:
            line = urwid.SelectableIcon(
                [("accent", n["label"]), ("dim", f"  [{n['kind']}]")], 0
            )
            row = urwid.AttrMap(urwid.Columns([line], dividechars=1), None, "list_focus")
            row.base_widget.node = n  # attach node dict to Columns
            self.walker.append(row)

    def widget(self):
        # left pane: the menu list (fills vertically)
        left = urwid.Pile([
            ('pack', urwid.Text(("dim", " ↑/↓, Enter=open, Backspace=back "))),
            ('weight', 1, urwid.LineBox(self.listbox, title=" Menu ")),
        ])
        # right pane: helpful info / placeholder
        right = urwid.LineBox(
            urwid.Filler(urwid.Text(
                "Select an item on the left.\n\n"
                "Kinds:\n"
                "  • menu   → open another submenu\n"
                "  • article→ open a single article\n"
                "  • list   → run a query and list matching articles\n\n"
                "Global: q quit   / focus filter (in list views)"),
            valign="top"), title=" Help ")

        # two columns
        return urwid.Columns([('fixed', 40, left), right], dividechars=1)

    def handle_key(self, key: str) -> bool:
        if key == "enter":
            focus, _ = self.listbox.get_focus()
            if not focus:
                return True
            node = focus.base_widget.node
            kind = node["kind"]
            if kind == "menu":
                self.app.router.push(MenuView(self.app, node["id"], node["label"]))
            elif kind == "article":
                self.app.router.push(ArticleDetailView(self.app, node["target_id"]))
            elif kind == "list":
                self.app.router.push(ArticleListView(self.app, node["query"], node["label"]))
            return True
        if key == "backspace":
            self.app.router.pop()
            return True
        return False

class ArticleListView(View):
    def __init__(self, app: "App", query: str, label: str = "Articles"):
        super().__init__(app)
        self.query = query or "*"
        self.title = f" KB • {label} "
        self.filter_edit = urwid.Edit(("dim", "/ Filter: "), "")
        self.walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.walker)
        self._refresh()

    def _refresh(self):
        q = self.filter_edit.edit_text.strip() or self.query
        arts = self.app.repo.search_articles(q)
        self.walker.clear()
        for a in arts:
            line = urwid.SelectableIcon(
                [("accent", a["title"]), ("dim", f" — {a.get('summary','')}")], 0
            )
            row = urwid.AttrMap(urwid.Columns([line], dividechars=1), None, "list_focus")
            row.base_widget.article = a
            self.walker.append(row)

    def widget(self):
        left = urwid.Pile([
            ('pack', self.filter_edit),
            ('pack', urwid.Divider()),
            ('weight', 1, urwid.LineBox(self.listbox, title=" Articles ")),
        ])
        right = urwid.LineBox(
            urwid.Filler(urwid.Text(
                "Enter=open article\n"
                "Backspace=back\n"
                "Type in / Filter and press Enter to apply"),
            valign="top"), title=" Tips ")
        return urwid.Columns([('fixed', 40, left), right], dividechars=1)

    def handle_key(self, key: str) -> bool:
        if key == "/":
            # focus filter
            return True
        if key == "enter":
            # If filter edit is focused and Enter pressed, re-run search.
            # Otherwise open selected article.
            # Determine focus within the left Pile:
            return self._enter()
        if key == "backspace":
            self.app.router.pop()
            return True
        return False

    def _enter(self) -> bool:
        # If filter is focused, apply filter
        # Figure out if filter has focus:
        # Simple heuristic: if cursor is visible in Edit, apply filter
        self._refresh()
        # Or open selected article if any:
        focus, _ = self.listbox.get_focus()
        if focus and hasattr(focus.base_widget, "article"):
            a = focus.base_widget.article
            self.app.router.push(ArticleDetailView(self.app, a["id"]))
        return True

class ArticleDetailView(View):
    def __init__(self, app: "App", article_id: str):
        super().__init__(app)
        self.article_id = article_id
        art = self.app.repo.get_article(article_id)
        self.title = f" KB • {art['title']} "
        self.text = urwid.Text(self._fmt(art), wrap="any")

    def _fmt(self, art: Dict) -> List[Tuple[str,str]]:
        title = art["title"]
        return [
            ("title", f"{title}\n"),
            ("dim", "-" * len(title) + "\n\n"),
            art.get("content",""),
            "\n\n", ("dim", "Backspace=back   q=quit"),
        ]

    def widget(self):
        return urwid.LineBox(urwid.Filler(self.text, valign="top"), title=" Article ")

    def handle_key(self, key: str) -> bool:
        if key == "backspace":
            self.app.router.pop()
            return True
        return False

# ---------------------------
# Application shell
# ---------------------------
class App:
    def __init__(self, repo: Repo):
        self.repo = repo
        self.router = Router(self)
        self.header = urwid.Text(("title", " KB "), align="center")
        self.footer = urwid.Text(("dim", " q:quit  Enter:open  Backspace:back "), align="right")

        frame = urwid.Frame(
            urwid.AttrWrap(self.router.placeholder, "bg"),
            header=self.header,
            footer=self.footer,
        )
        self.loop = urwid.MainLoop(
            frame,
            palette=PALETTE,
            unhandled_input=self._handle_global,
        )

    def set_header(self, text: str):
        self.header.set_text(("title", text))

    def _handle_global(self, key: str):
        # Give the current view first shot
        if self.router.stack and self.router.top().handle_key(key):
            return
        # Globals
        if key in ("q", "Q"):
            raise urwid.ExitMainLoop()

    def run(self):
        # Start at root menu (parent_id=None)
        self.router.push(MenuView(self, None, "Home"))
        self.loop.run()

# ---------------------------
# Entry
# ---------------------------
if __name__ == "__main__":
    app = App(Repo(DB_PATH))
    app.run()
