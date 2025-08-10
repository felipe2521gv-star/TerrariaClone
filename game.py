"""
TerrariaClone: A simplified sandbox adventure game inspired by Terraria.

This game uses the pygame library to implement a small 2D world where a player
can explore, mine resources, place blocks, fight enemies and defeat a boss.

Controls
--------
• Move left/right: A/D or Left/Right arrow keys
• Jump: W, Up arrow or Spacebar
• Mine block: Left mouse button (within reach)
• Place block: Right mouse button (within reach)
• Change selected block: Number keys 1–4 (dirt, stone, ore, wood)

The goal of the game is to gather enough ore to spawn the boss.  Once the boss
is defeated the game will display a victory message.  A basic day/night cycle
spawns zombies during the night to keep the player on their toes.

This file can be run directly using ``python game.py`` provided that pygame
is installed.  It expects a ``resources`` folder in the same directory
containing several PNG images: dirt.png, grass.png, stone.png, ore.png,
wood.png, player.png, enemy.png and boss.png.  These assets are scaled
dynamically to fit the configured tile size.
"""

import os
import sys
import random
import pygame


# -----------------------------------------------------------------------------
# Configuration constants
#
SCREEN_WIDTH = 960  # width of the window in pixels
SCREEN_HEIGHT = 540  # height of the window in pixels
TILE_SIZE = 32       # size of a single tile in pixels

WORLD_WIDTH = 100    # width of the world in tiles
WORLD_HEIGHT = 60    # height of the world in tiles

GRAVITY = 0.6        # downward acceleration per frame
PLAYER_SPEED = 4     # horizontal movement speed of the player
PLAYER_JUMP = 12     # initial upward velocity when jumping

ENEMY_SPEED = 1.5    # horizontal movement speed of enemies
ENEMY_JUMP_CHANCE = 0.01  # chance per frame that an enemy will jump

DAY_LENGTH = 60 * 20  # number of frames per half-day (approx 20 seconds at 60 FPS)
ENEMY_SPAWN_INTERVAL = 4 * 60  # spawn enemy every 4 seconds during night
BOSS_SPAWN_ORE_COUNT = 10  # number of ore required to spawn the boss


# -----------------------------------------------------------------------------
# Helper functions
#

def load_image(name, size=None):
    """Load an image from the resources folder and optionally scale it.

    Parameters
    ----------
    name : str
        Filename inside the resources directory (e.g. 'dirt.png').
    size : tuple[int, int] or None
        Desired width and height.  If None the original image is returned.

    Returns
    -------
    pygame.Surface
        The loaded (and scaled) surface with per‑pixel alpha.
    """
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, 'resources', name)
    image = pygame.image.load(path).convert_alpha()
    if size:
        image = pygame.transform.smoothscale(image, size)
    return image


def generate_world(width, height):
    """Procedurally generate a simple overworld.

    The surface height undulates slightly to create hills.  The topmost tile is
    grass, the next few layers are dirt, and deeper layers are stone with a
    chance of ore.  A value of 0 represents air.

    Parameters
    ----------
    width : int
        Number of tiles horizontally.
    height : int
        Number of tiles vertically.

    Returns
    -------
    list[list[int]]
        A 2‑D array of tile identifiers.
    """
    world = [[0 for _ in range(width)] for _ in range(height)]
    base = height // 2
    current_height = base
    for x in range(width):
        # Randomly adjust the surface height to create gentle hills
        current_height += random.choice([-1, 0, 1])
        current_height = max(base - 4, min(base + 4, current_height))
        for y in range(current_height, height):
            if y == current_height:
                # surface tile: grass
                world[y][x] = 2
            elif y < current_height + 5:
                # just below surface: dirt
                world[y][x] = 1
            else:
                # deeper: stone or ore
                world[y][x] = 4 if random.random() < 0.05 else 3
    return world


def is_solid(tile_id):
    """Return True if the tile_id corresponds to a solid block."""
    return tile_id != 0


# -----------------------------------------------------------------------------
# Entity classes
#

class Player(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, images: dict[str, pygame.Surface]):
        super().__init__()
        self.images = images
        self.image = images['player']
        self.rect = self.image.get_rect()
        # Position the rect such that the bottom center is at (x, y)
        self.rect.centerx = x
        self.rect.bottom = y
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.on_ground = False
        self.health = 100
        # Inventory counts for each resource type
        self.inventory = {
            'dirt': 0,
            'stone': 0,
            'ore': 0,
            'wood': 0,
        }
        # Currently selected block to place (key corresponds to inventory)
        self.selected = 'dirt'
        # Hurt cooldown to prevent taking continuous damage
        self.hurt_cooldown = 0

    def handle_input(self):
        keys = pygame.key.get_pressed()
        self.vel_x = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.vel_x = -PLAYER_SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.vel_x = PLAYER_SPEED
        # Jump if on ground
        if (keys[pygame.K_w] or keys[pygame.K_UP] or keys[pygame.K_SPACE]) and self.on_ground:
            self.vel_y = -PLAYER_JUMP
            self.on_ground = False
        # Change selected block with number keys
        if keys[pygame.K_1]:
            self.selected = 'dirt'
        if keys[pygame.K_2]:
            self.selected = 'stone'
        if keys[pygame.K_3]:
            self.selected = 'ore'
        if keys[pygame.K_4]:
            self.selected = 'wood'

    def update(self, world):
        # Apply gravity
        self.vel_y += GRAVITY
        # Horizontal movement
        original_x = self.rect.x
        self.rect.x += int(self.vel_x)
        self._resolve_collisions(world, dx=self.vel_x, dy=0)
        # Vertical movement
        original_y = self.rect.y
        self.rect.y += int(self.vel_y)
        self.on_ground = False
        self._resolve_collisions(world, dx=0, dy=self.vel_y)
        # Hurt cooldown timer
        if self.hurt_cooldown > 0:
            self.hurt_cooldown -= 1

    def _resolve_collisions(self, world, dx: float, dy: float):
        # Determine which tiles intersect with the player after movement
        # We'll check the four corners of the player's rectangle
        corners = [
            (self.rect.left, self.rect.top),
            (self.rect.right - 1, self.rect.top),
            (self.rect.left, self.rect.bottom - 1),
            (self.rect.right - 1, self.rect.bottom - 1),
        ]
        for corner_x, corner_y in corners:
            tile_x = corner_x // TILE_SIZE
            tile_y = corner_y // TILE_SIZE
            if 0 <= tile_x < WORLD_WIDTH and 0 <= tile_y < WORLD_HEIGHT:
                tile = world[tile_y][tile_x]
                if is_solid(tile):
                    if dy > 0:
                        # Falling – bump head on tile below
                        self.rect.bottom = tile_y * TILE_SIZE
                        self.vel_y = 0
                        self.on_ground = True
                    elif dy < 0:
                        # Jumping – bump head on tile above
                        self.rect.top = (tile_y + 1) * TILE_SIZE
                        self.vel_y = 0
                    if dx > 0:
                        # Moving right – hit left side of tile
                        self.rect.right = tile_x * TILE_SIZE
                    elif dx < 0:
                        # Moving left – hit right side of tile
                        self.rect.left = (tile_x + 1) * TILE_SIZE

    def mine_block(self, world, camera, mouse_pos):
        """Attempt to mine a block under the mouse cursor."""
        # Compute world coordinates of the mouse click
        mx, my = mouse_pos
        world_x = (mx + camera[0]) // TILE_SIZE
        world_y = (my + camera[1]) // TILE_SIZE
        # Check distance from player – can't mine too far away
        px = self.rect.centerx // TILE_SIZE
        py = self.rect.centery // TILE_SIZE
        if abs(world_x - px) > 4 or abs(world_y - py) > 4:
            return
        if 0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT:
            tile = world[world_y][world_x]
            # Only mine if not air and not hitting bedrock bottom row (y == WORLD_HEIGHT-1)
            if tile != 0 and world_y < WORLD_HEIGHT - 1:
                # Add block to inventory
                if tile == 1:
                    self.inventory['dirt'] += 1
                elif tile == 2:
                    self.inventory['dirt'] += 1
                elif tile == 3:
                    self.inventory['stone'] += 1
                elif tile == 4:
                    self.inventory['ore'] += 1
                elif tile == 5:
                    self.inventory['wood'] += 1
                # Remove the block
                world[world_y][world_x] = 0

    def place_block(self, world, camera, mouse_pos):
        """Attempt to place the currently selected block under the mouse cursor."""
        # Only place if there is at least one of the selected item in inventory
        if self.inventory.get(self.selected, 0) <= 0:
            return
        mx, my = mouse_pos
        world_x = (mx + camera[0]) // TILE_SIZE
        world_y = (my + camera[1]) // TILE_SIZE
        # Check for valid placement
        if 0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT:
            if world[world_y][world_x] == 0:
                # Prevent placing inside the player
                tile_rect = pygame.Rect(world_x * TILE_SIZE, world_y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                if not self.rect.colliderect(tile_rect):
                    # Map item key to tile id
                    if self.selected == 'dirt':
                        world[world_y][world_x] = 1
                    elif self.selected == 'stone':
                        world[world_y][world_x] = 3
                        # Use stone tile for placed stone
                    elif self.selected == 'ore':
                        world[world_y][world_x] = 4
                    elif self.selected == 'wood':
                        world[world_y][world_x] = 5
                    # Deduct from inventory
                    self.inventory[self.selected] -= 1

    def draw(self, surface, camera):
        # Draw player adjusted for camera
        surface.blit(self.image, (self.rect.x - camera[0], self.rect.y - camera[1]))


class Enemy(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, images: dict[str, pygame.Surface]):
        super().__init__()
        self.images = images
        self.image = images['enemy']
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.bottom = y
        self.vel_x = random.choice([-ENEMY_SPEED, ENEMY_SPEED])
        self.vel_y = 0.0
        self.on_ground = False
        self.health = 30
        self.hurt_cooldown = 0

    def update(self, world, player: Player):
        # Follow the player if horizontal distance is small
        if player.rect.centerx < self.rect.centerx:
            self.vel_x = -ENEMY_SPEED
        else:
            self.vel_x = ENEMY_SPEED
        # Randomly jump to get past small obstacles
        if self.on_ground and random.random() < ENEMY_JUMP_CHANCE:
            self.vel_y = -PLAYER_JUMP * 0.8
            self.on_ground = False
        # Gravity
        self.vel_y += GRAVITY
        # Horizontal move
        self.rect.x += int(self.vel_x)
        self._resolve_collisions(world, dx=self.vel_x, dy=0)
        # Vertical move
        self.rect.y += int(self.vel_y)
        self.on_ground = False
        self._resolve_collisions(world, dx=0, dy=self.vel_y)
        # Hurt cooldown timer
        if self.hurt_cooldown > 0:
            self.hurt_cooldown -= 1

    def _resolve_collisions(self, world, dx: float, dy: float):
        corners = [
            (self.rect.left, self.rect.top),
            (self.rect.right - 1, self.rect.top),
            (self.rect.left, self.rect.bottom - 1),
            (self.rect.right - 1, self.rect.bottom - 1),
        ]
        for corner_x, corner_y in corners:
            tile_x = corner_x // TILE_SIZE
            tile_y = corner_y // TILE_SIZE
            if 0 <= tile_x < WORLD_WIDTH and 0 <= tile_y < WORLD_HEIGHT:
                tile = world[tile_y][tile_x]
                if is_solid(tile):
                    if dy > 0:
                        # Falling – land on block
                        self.rect.bottom = tile_y * TILE_SIZE
                        self.vel_y = 0
                        self.on_ground = True
                    elif dy < 0:
                        self.rect.top = (tile_y + 1) * TILE_SIZE
                        self.vel_y = 0
                    if dx > 0:
                        self.rect.right = tile_x * TILE_SIZE
                    elif dx < 0:
                        self.rect.left = (tile_x + 1) * TILE_SIZE
        # Keep within world bounds
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > WORLD_WIDTH * TILE_SIZE:
            self.rect.right = WORLD_WIDTH * TILE_SIZE

    def draw(self, surface, camera):
        surface.blit(self.image, (self.rect.x - camera[0], self.rect.y - camera[1]))

    def damage(self, amount: int):
        self.health -= amount


class Boss(pygame.sprite.Sprite):
    def __init__(self, x: int, y: int, images: dict[str, pygame.Surface]):
        super().__init__()
        self.images = images
        # Boss image is larger; scale to 2× tile size
        raw_img = images['boss']
        factor = 2
        self.image = pygame.transform.smoothscale(raw_img, (TILE_SIZE * factor * 2, TILE_SIZE * factor * 2))
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.bottom = y
        self.vel_x = ENEMY_SPEED * 1.5
        self.vel_y = 0.0
        self.on_ground = False
        self.health = 250
        self.hurt_cooldown = 0

    def update(self, world, player: Player):
        # Track the player horizontally
        if player.rect.centerx < self.rect.centerx:
            self.vel_x = -abs(self.vel_x)
        else:
            self.vel_x = abs(self.vel_x)
        # Occasionally jump to overcome obstacles
        if self.on_ground and random.random() < 0.02:
            self.vel_y = -PLAYER_JUMP  # jump higher
            self.on_ground = False
        # Gravity
        self.vel_y += GRAVITY
        # Apply movement
        self.rect.x += int(self.vel_x)
        self._resolve_collisions(world, dx=self.vel_x, dy=0)
        self.rect.y += int(self.vel_y)
        self.on_ground = False
        self._resolve_collisions(world, dx=0, dy=self.vel_y)
        if self.hurt_cooldown > 0:
            self.hurt_cooldown -= 1

    def _resolve_collisions(self, world, dx: float, dy: float):
        corners = [
            (self.rect.left, self.rect.top),
            (self.rect.right - 1, self.rect.top),
            (self.rect.left, self.rect.bottom - 1),
            (self.rect.right - 1, self.rect.bottom - 1),
        ]
        for corner_x, corner_y in corners:
            tile_x = corner_x // TILE_SIZE
            tile_y = corner_y // TILE_SIZE
            if 0 <= tile_x < WORLD_WIDTH and 0 <= tile_y < WORLD_HEIGHT:
                tile = world[tile_y][tile_x]
                if is_solid(tile):
                    if dy > 0:
                        self.rect.bottom = tile_y * TILE_SIZE
                        self.vel_y = 0
                        self.on_ground = True
                    elif dy < 0:
                        self.rect.top = (tile_y + 1) * TILE_SIZE
                        self.vel_y = 0
                    if dx > 0:
                        self.rect.right = tile_x * TILE_SIZE
                    elif dx < 0:
                        self.rect.left = (tile_x + 1) * TILE_SIZE
        # Keep within world bounds
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > WORLD_WIDTH * TILE_SIZE:
            self.rect.right = WORLD_WIDTH * TILE_SIZE

    def draw(self, surface, camera):
        surface.blit(self.image, (self.rect.x - camera[0], self.rect.y - camera[1]))

    def damage(self, amount: int):
        self.health -= amount


# -----------------------------------------------------------------------------
# Rendering and UI
#

def draw_world(surface, world, images, camera):
    """Draw the visible portion of the world based on the camera offset."""
    screen_tiles_x = (SCREEN_WIDTH // TILE_SIZE) + 2
    screen_tiles_y = (SCREEN_HEIGHT // TILE_SIZE) + 2
    start_x = camera[0] // TILE_SIZE
    start_y = camera[1] // TILE_SIZE
    for y in range(start_y, start_y + screen_tiles_y):
        if 0 <= y < WORLD_HEIGHT:
            for x in range(start_x, start_x + screen_tiles_x):
                if 0 <= x < WORLD_WIDTH:
                    tile = world[y][x]
                    if tile != 0:
                        # Map tile ids to image keys
                        if tile == 1:
                            img = images['dirt']
                        elif tile == 2:
                            img = images['grass']
                        elif tile == 3:
                            img = images['stone']
                        elif tile == 4:
                            img = images['ore']
                        elif tile == 5:
                            img = images['wood']
                        else:
                            img = None
                        if img:
                            surface.blit(img, (x * TILE_SIZE - camera[0], y * TILE_SIZE - camera[1]))


def draw_inventory(surface, player: Player, images):
    """Draw a simple hotbar at the bottom of the screen."""
    bar_height = 40
    y = SCREEN_HEIGHT - bar_height
    pygame.draw.rect(surface, (0, 0, 0, 180), (0, y, SCREEN_WIDTH, bar_height))
    font = pygame.font.SysFont('arial', 16)
    # Define order of items in hotbar
    items = ['dirt', 'stone', 'ore', 'wood']
    slot_size = 40
    padding = 5
    x_offset = 10
    for idx, item_key in enumerate(items):
        rect = pygame.Rect(x_offset + idx * (slot_size + padding), y + 5, slot_size, slot_size)
        # Highlight selected slot
        if player.selected == item_key:
            pygame.draw.rect(surface, (200, 200, 50), rect.inflate(4, 4), 2)
        # Draw background
        pygame.draw.rect(surface, (80, 80, 80), rect)
        # Draw item icon (scaled block texture)
        if item_key == 'dirt':
            icon = pygame.transform.smoothscale(images['dirt'], (slot_size - 8, slot_size - 8))
        elif item_key == 'stone':
            icon = pygame.transform.smoothscale(images['stone'], (slot_size - 8, slot_size - 8))
        elif item_key == 'ore':
            icon = pygame.transform.smoothscale(images['ore'], (slot_size - 8, slot_size - 8))
        elif item_key == 'wood':
            icon = pygame.transform.smoothscale(images['wood'], (slot_size - 8, slot_size - 8))
        surface.blit(icon, (rect.x + 4, rect.y + 4))
        # Draw count
        count = player.inventory[item_key]
        count_surf = font.render(str(count), True, (255, 255, 255))
        surface.blit(count_surf, (rect.right - count_surf.get_width() - 4, rect.bottom - count_surf.get_height() - 4))


def draw_health(surface, player: Player):
    """Draw a health bar at the top left."""
    max_width = 200
    height = 20
    x, y = 10, 10
    # Background
    pygame.draw.rect(surface, (80, 80, 80), (x, y, max_width, height))
    # Health amount
    health_width = max(0, min(max_width, int(max_width * (player.health / 100))))
    pygame.draw.rect(surface, (200, 40, 40), (x, y, health_width, height))
    # Border
    pygame.draw.rect(surface, (255, 255, 255), (x, y, max_width, height), 2)


# -----------------------------------------------------------------------------
# Main game loop
#

def run_game():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption('TerrariaClone')
    clock = pygame.time.Clock()

    # Load and scale images
    images = {
        'dirt': load_image('dirt.png', (TILE_SIZE, TILE_SIZE)),
        'grass': load_image('grass.png', (TILE_SIZE, TILE_SIZE)),
        'stone': load_image('stone.png', (TILE_SIZE, TILE_SIZE)),
        'ore': load_image('ore.png', (TILE_SIZE, TILE_SIZE)),
        'wood': load_image('wood.png', (TILE_SIZE, TILE_SIZE)),
        'player': load_image('player.png', (TILE_SIZE, int(TILE_SIZE * 1.5))),
        'enemy': load_image('enemy.png', (TILE_SIZE, int(TILE_SIZE * 1.5))),
        'boss': load_image('boss.png'),
    }

    # Generate the world
    world = generate_world(WORLD_WIDTH, WORLD_HEIGHT)

    # Create player at surface level near the left side
    # Find ground height at x coordinate 5
    ground_y = 0
    for y in range(WORLD_HEIGHT):
        if world[y][5] != 0:
            ground_y = y
            break
    player = Player(5 * TILE_SIZE, ground_y * TILE_SIZE, images)

    # Enemy group
    enemies = pygame.sprite.Group()
    enemy_spawn_timer = 0
    # Boss
    boss = None
    boss_spawned = False
    boss_defeated = False

    # Day/night timer
    time_of_day = 0
    day_count = 0
    font = pygame.font.SysFont('arial', 20)

    # Story message timer
    story_timer = 600  # frames (~10 seconds at 60fps)
    show_story = True

    running = True
    while running:
        dt = clock.tick(60)
        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Left click – mine block
                player.mine_block(world, (camera_x, camera_y), event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                # Right click – place block
                player.place_block(world, (camera_x, camera_y), event.pos)

        # Handle keyboard input continuously
        player.handle_input()

        # Update player
        player.update(world)
        # Update camera (center on player)
        camera_x = player.rect.centerx - SCREEN_WIDTH // 2
        camera_y = player.rect.centery - SCREEN_HEIGHT // 2
        # Clamp camera within world bounds
        camera_x = max(0, min(camera_x, WORLD_WIDTH * TILE_SIZE - SCREEN_WIDTH))
        camera_y = max(0, min(camera_y, WORLD_HEIGHT * TILE_SIZE - SCREEN_HEIGHT))

        # Day/night cycle update
        time_of_day += 1
        if time_of_day >= DAY_LENGTH:
            time_of_day = 0
            day_count += 1
        # Determine sky color (simple gradient between day and night)
        t = time_of_day / DAY_LENGTH
        # t in [0,1] mapping: 0 = dawn, 0.5 = dusk; we oscillate
        brightness = 0.5 + 0.5 * (1 - abs(0.5 - t) * 2)
        day_color = pygame.Color(100, 150, 255)
        night_color = pygame.Color(20, 30, 70)
        # Linear interpolation between night and day based on brightness
        sky_color = (
            int(night_color.r + (day_color.r - night_color.r) * brightness),
            int(night_color.g + (day_color.g - night_color.g) * brightness),
            int(night_color.b + (day_color.b - night_color.b) * brightness),
        )

        # Enemy spawning at night
        is_night = brightness < 0.5
        if is_night and not boss_defeated:
            enemy_spawn_timer += 1
            if enemy_spawn_timer >= ENEMY_SPAWN_INTERVAL:
                enemy_spawn_timer = 0
                # Try to spawn a zombie at a random x away from the player
                spawn_x = random.randint(0, WORLD_WIDTH - 1)
                # Avoid spawning right on top of player
                if abs(spawn_x - player.rect.centerx // TILE_SIZE) > 10:
                    # Find ground
                    for y in range(WORLD_HEIGHT):
                        if world[y][spawn_x] != 0:
                            spawn_y = y
                            break
                    # Spawn enemy slightly above ground
                    enemy = Enemy(spawn_x * TILE_SIZE, spawn_y * TILE_SIZE, images)
                    enemies.add(enemy)

        # Spawn boss if conditions met
        if not boss_spawned and player.inventory['ore'] >= BOSS_SPAWN_ORE_COUNT:
            # Spawn boss near the player
            bx = player.rect.centerx
            # Find ground at player's x
            gx = bx // TILE_SIZE
            gy = 0
            for y in range(WORLD_HEIGHT):
                if world[y][int(gx)] != 0:
                    gy = y
                    break
            boss = Boss(bx, gy * TILE_SIZE, images)
            boss_spawned = True
            show_story = True
            story_timer = 600

        # Update enemies
        for enemy in list(enemies):
            enemy.update(world, player)
            # Damage player on collision
            if enemy.rect.colliderect(player.rect):
                if player.hurt_cooldown == 0:
                    player.health -= 10
                    player.hurt_cooldown = 60  # invincibility frames
                    # Knockback player slightly
                    if enemy.rect.centerx < player.rect.centerx:
                        player.vel_x += 2
                    else:
                        player.vel_x -= 2
            # If enemy falls off world or dies, remove
            if enemy.rect.top > WORLD_HEIGHT * TILE_SIZE or enemy.health <= 0:
                enemies.remove(enemy)

        # Update boss
        if boss and not boss_defeated:
            boss.update(world, player)
            # Damage player on collision
            if boss.rect.colliderect(player.rect):
                if player.hurt_cooldown == 0:
                    player.health -= 20
                    player.hurt_cooldown = 60
                    if boss.rect.centerx < player.rect.centerx:
                        player.vel_x += 4
                    else:
                        player.vel_x -= 4
            # Remove boss if defeated
            if boss.health <= 0:
                boss_defeated = True
                show_story = True
                story_timer = 600

        # Check for game over
        if player.health <= 0:
            running = False

        # Clear screen
        screen.fill(sky_color)
        # Draw world
        draw_world(screen, world, images, (camera_x, camera_y))
        # Draw entities
        player.draw(screen, (camera_x, camera_y))
        for enemy in enemies:
            enemy.draw(screen, (camera_x, camera_y))
        if boss and not boss_defeated:
            boss.draw(screen, (camera_x, camera_y))
        # Draw UI
        draw_inventory(screen, player, images)
        draw_health(screen, player)

        # Draw story text
        if show_story:
            story_timer -= 1
            if story_timer <= 0:
                show_story = False
            else:
                if not boss_defeated:
                    if not boss_spawned:
                        text = 'Gather resources and defeat the boss to restore the world.'
                    else:
                        text = 'The boss has awoken!  Defeat it to save the land.'
                else:
                    text = 'You have defeated the boss!  Peace has returned.'
                story_surf = font.render(text, True, (255, 255, 255))
                screen.blit(story_surf, ((SCREEN_WIDTH - story_surf.get_width()) // 2, 50))

        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    run_game()