import os, sys, json, math, random, time
import pygame
import requests

# --------------- SETTINGS ---------------
WIDTH, HEIGHT = 800, 600
FPS = 60
ASSETS = "assets"

ROBOTO_REGULAR = os.path.join(ASSETS, "Roboto-Regular.ttf")
ROBOTO_BOLD    = os.path.join(ASSETS, "Roboto-Bold.ttf")

HIGHSCORE_FILE = "highscore.txt"

# --------------- IMAGE REGISTRY ---------------
class ImageRegistry:
    def __init__(self):
        self.cache = {}

        # Backgrounds
        self.bg_menu   = self._load("menu.png")
        self.bg_game   = self._load("workscene.png")
        self.bg_end    = self._load("ending.png")
        self.bg_black  = self._load("black.png")
        self.play_btn  = self._load("playbutton.png")
        self.input_box = self._load("inputbox.png")
        self.title     = self._load("logo.png")
        self.fade_img  = self._load("black.png")

    def _load(self, filename):
        path = os.path.join(ASSETS, filename)
        if not os.path.exists(path):
            surf = pygame.Surface((1,1)).convert_alpha()
            surf.fill((0,0,0,0))
            return surf
        if filename.lower().endswith(".png") or filename.lower().endswith(".jpg"):
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(img, img.get_size())
        return pygame.Surface((1,1)).convert_alpha()

# --------------- TEXT RENDERING (images) ---------------
class Text:
    def __init__(self, size=28, bold=False, color=(0,0,0)):
        self.font = pygame.font.Font(ROBOTO_BOLD if bold else ROBOTO_REGULAR, size)
        self.color = color

    def render(self, message):
        return self.font.render(str(message), True, self.color)

# --------------- SCENE SYSTEM ---------------
class Scene:
    def __init__(self, game):
        self.game = game

    def handle_event(self, e): pass
    def update(self, dt): pass
    def draw(self, screen): pass

class SceneManager:
    def __init__(self, game):
        self.game = game
        self.current = None
        self.next_scene = None
        self.fading = False
        self.fade_alpha = 0
        self.fade_speed = 15

    def set(self, scene):
        self.current = scene

    def request(self, scene):
        self.next_scene = scene
        self.fading = True
        self.fade_alpha = 0

    def update(self, dt):
        if self.fading:
            self.fade_alpha += self.fade_speed
            if self.fade_alpha >= 255:
                self.current = self.next_scene
                self.next_scene = None
                self.fade_alpha = 255
                time.sleep(0.5)
                self.fading = False
        else:
            if self.current:
                self.current.update(dt)

    def draw(self, screen):
        if self.current:
            self.current.draw(screen)
        if self.fading or self.fade_alpha > 0:
            overlay = self.game.images.fade_img.copy()
            overlay.set_alpha(min(255, self.fade_alpha))
            screen.blit(overlay, (0, 0))
            if not self.fading and self.fade_alpha > 0:
                self.fade_alpha = 0

# --------------- WEATHER CLIENT ---------------
class WeatherClient:
    def get_week_temps(self):
        base = 22
        temps = [base - 10, base - 6, base - 2, base + 2, base + 6, base + 10]
        return temps

# --------------- GAME LOGIC ---------------
def label_six(temps_ascending):
    assert len(temps_ascending) == 6
    t = temps_ascending
    mapping = {
        "coldest": t[0],
        "colder":  t[1],
        "normal1": t[2],
        "normal2": t[3],
        "hotter":  t[4],
        "hottest": t[5],
    }
    ordered_labels = [("Hottest", t[5]), ("Hotter", t[4]), ("Normal", t[3]),
                      ("Normal", t[2]), ("Colder", t[1]), ("Coldest", t[0])]
    return mapping, ordered_labels

def range_from_labels(label_map, low_key, high_key):
    low = int(label_map[low_key])
    high = int(label_map[high_key])
    if low > high:
        low, high = high, low
    return low, high

QUESTIONS = [
    {
        "id": 1,
        "text": "It's warm out there.",
        "bounds": ("normal1", "hotter")
    },
    {
        "id": 2,
        "text": "It's cool out there.",
        "bounds": ("colder", "normal2")
    },
    {
        "id": 3,
        "text": "The world is boiling!",
        "bounds": ("hotter", "hottest")
    },
    {
        "id": 4,
        "text": "The world went cold!",
        "bounds": ("coldest", "colder")
    },
    {
        "id": 5,
        "text": "It's a comfortable weather.",
        "bounds": ("normal1", "normal2")
    },
]

# --------------- SCENES ---------------
class MenuScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.title_txt = Text(48, bold=True)
        self.info_txt  = Text(32, bold=True)
        self.hs_txt    = Text(28, bold=True)
    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_p:
                self.game.start_new_game()

    def update(self, dt):
        pass

    def draw(self, screen):
        img = self.game.images
        screen.blit(img.bg_menu, (0,0))

        # Title
        title = img.title
        screen.blit(title, ((WIDTH - title.get_width())//2, 80))

        # High score
        hs_val = self.game.load_highscore()
        hs = self.hs_txt.render(f"High Score: {hs_val}")
        screen.blit(hs, ((WIDTH - hs.get_width())//2 - 10, 280))

        play_y = HEIGHT//2 - 50

        tip = self.info_txt.render('Press "P" to Play')
        screen.blit(tip, ((WIDTH - tip.get_width())//2 - 10, play_y + img.play_btn.get_height() + 12))

class GameScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.h1 = Text(24, bold=True)
        self.h2 = Text(22, bold=False)
        self.hint_txt = Text(28, bold=True)
        self.small = Text(20, bold=False)

        self.weather = WeatherClient()
        self.week = self.weather.get_week_temps()
        self.label_map, self.ordered_labels = label_six(self.week)

        self.questions = random.sample(QUESTIONS, 4)
        self.q_index = 0
        self.lives = 4
        self.score = 0

        self.input_str = ""
        self.current_hint = ""

        self._recalc_range()

    def _recalc_range(self):
        low_key, high_key = self.questions[self.q_index]["bounds"]
        self.accept_low, self.accept_high = range_from_labels(self.label_map, low_key, high_key)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE:
                self.input_str = self.input_str[:-1]
            elif e.key == pygame.K_MINUS:
                if len(self.input_str) == 0:
                    self.input_str = "-"
            elif e.key == pygame.K_RETURN:
                self._submit_guess()
            else:
                if e.unicode.isdigit():
                    self.input_str += e.unicode

    def _submit_guess(self):
        if self.input_str == "" or self.input_str == "-":
            return
        guess = int(self.input_str)

        if guess < -273 or guess > 273:
            pygame.quit()
            sys.exit()

        if -273 <= guess <= -100:
            self.game.to_special("THEN THE WORLD WAS COVERED IN FROST.")
            return
        if guess > 100:
            self.game.to_special("THEN THE WORLD WAS COVERED IN ASHES.")
            return

        if self.accept_low <= guess <= self.accept_high:
            self.score += 1
            self.q_index += 1
            if self.q_index >= 3:
                self.game.to_ending(hired=True, score=self.score)
                return
            self.lives = 4
            self.input_str = ""
            self.current_hint = ""
            self._recalc_range()
        else:
            if guess < self.accept_low:
                diff = self.accept_low - guess
                self.current_hint = "<" if diff <= 2 else "<<"
            elif guess > self.accept_high:
                diff = guess - self.accept_high
                self.current_hint = ">" if diff <= 2 else ">>"

            self.lives -= 1
            self.input_str = ""
            if self.lives <= 0:
                self.game.to_ending(hired=False, score=self.score)

    def update(self, dt):
        pass

    def draw(self, screen):
        img = self.game.images
        screen.blit(img.bg_game, (0,0))

        q = self.questions[self.q_index]
        qnum = self.h1.render(f"{self.q_index+1}")
        qtext = self.h2.render(q["text"])
        if self.q_index <= 3:
            screen.blit(qnum, (110, 95))
            screen.blit(qtext, (172, 75))

        panel_x, panel_y = 60, 120
        y = panel_y + 60
        extra = 0
        for label, val in self.ordered_labels: 
            line = self.small.render(f"{label}: {val}°C")
            screen.blit(line, (panel_x + 20, y))
            y += 45 + extra
            if extra < 6:
                extra +=2
            else:
                extra = 0

        extra = 0
        lives_txt = self.h1.render(f"{self.lives}")
        screen.blit(lives_txt, (100, 477))

        # Right: hint
        hint_s = self.hint_txt.render(self.current_hint if self.current_hint else "")
        screen.blit(hint_s, (WIDTH - 40 - hint_s.get_width(), 340))

        # Input area
        input_x, input_y = 40, 400
        display_val = self.h1.render(self.input_str if self.input_str else "Type number, Enter to submit")
        screen.blit(display_val, ((input_x + 16)*2 + 55, input_y + (img.input_box.get_height() - display_val.get_height())//2 + 35))

class EndingScene(Scene):
    def __init__(self, game, hired, score):
        super().__init__(game)
        self.hired = hired
        self.score = score
        self.big = Text(48, bold=True)
        self.mid = Text(28, bold=True)
        self.small = Text(22, bold=True)

        # high score save
        self.game.save_highscore(score)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_q:
                self.game.to_menu()

    def update(self, dt):
        pass

    def draw(self, screen):
        img = self.game.images
        screen.blit(img.bg_end, (0,0))

        msg = "HIRED" if self.hired else "FIRED"
        title = self.big.render(msg)
        screen.blit(title, ((WIDTH - title.get_width())//2 - 10, 140))

        score_t = self.mid.render(f"Score: {self.score}/3")
        screen.blit(score_t, ((WIDTH - score_t.get_width())//2 - 10, 220))

        tip = self.small.render('Press "Q" to return.')
        screen.blit(tip, ((WIDTH - tip.get_width())//2, HEIGHT - 60))

class SpecialScene(Scene):
    def __init__(self, game, message):
        super().__init__(game)
        self.message = message
        self.big = Text(36, True, (255, 255, 255))

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_q:
                self.game.to_menu()

    def update(self, dt):
        pass

    def draw(self, screen):
        screen.blit(self.game.images.bg_black, (0,0))
        t = self.big.render(self.message.upper())
        screen.blit(t, ((WIDTH - t.get_width())//2, (HEIGHT - t.get_height())//2))
        tip = Text(22, True, (255, 255, 255)).render('Press "Q" to return.')
        screen.blit(tip, ((WIDTH - tip.get_width())//2, HEIGHT - 60))

# --------------- GAME APP ---------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("WeatherWhether")
        self.clock = pygame.time.Clock()
        self.images = ImageRegistry()

        self.manager = SceneManager(self)
        self.manager.set(MenuScene(self))

    # Scene helpers
    def to_menu(self):
        self.manager.request(MenuScene(self))

    def start_new_game(self):
        self.manager.request(GameScene(self))

    def to_ending(self, hired, score):
        self.manager.request(EndingScene(self, hired, score))

    def to_special(self, message):
        self.manager.request(SpecialScene(self, message))

    # High score
    def load_highscore(self):
        try:
            with open(HIGHSCORE_FILE, "r") as f:
                content = f.read().strip()
                if content == '':
                    return 0
                return int(content)
        except (ValueError, FileNotFoundError) as e:
            return 0

    def save_highscore(self, score):
        old = self.load_highscore()
        if score > old:
            try:
                with open(HIGHSCORE_FILE, "w") as f:
                    f.write(str(score))
            except Exception:
                pass

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                else:
                    if self.manager.current:
                        self.manager.current.handle_event(e)

            self.manager.update(dt)
            self.manager.draw(self.screen)
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    Game().run()
