const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PORT = process.env.PORT || 3000;
const COLS = 40;
const ROWS = 30;
const TICK_MS = 150;
const FOOD_COUNT = 5;
const RESPAWN_DELAY_MS = 3000;
const GOLD_INTERVAL_MS = 60000;
const GOLD_POINTS = 10;
const WIN_SCORE = 100;

const COLORS = [
  '#22c55e', '#3b82f6', '#f59e0b', '#ef4444',
  '#a855f7', '#ec4899', '#14b8a6', '#f97316',
];

const rooms = new Map();

function genRoomCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code;
  do {
    code = '';
    for (let i = 0; i < 4; i++) code += chars[Math.floor(Math.random() * chars.length)];
  } while (rooms.has(code));
  return code;
}

function createRoom(code, roomName, maxPlayers) {
  const room = {
    code,
    roomName,
    maxPlayers,
    hostId: null,
    players: new Map(),
    food: [],
    goldFood: [],
    winner: null,
    state: 'lobby',
    tickInterval: null,
    goldInterval: null,
    nextPlayerId: 1,
  };
  rooms.set(code, room);
  return room;
}

function destroyRoom(code) {
  const room = rooms.get(code);
  if (!room) return;
  clearInterval(room.tickInterval);
  clearInterval(room.goldInterval);
  rooms.delete(code);
}

function spawnPos(room) {
  const occupied = new Set();
  for (const p of room.players.values()) {
    if (p.alive) for (const s of p.snake) occupied.add(`${s.x},${s.y}`);
  }
  for (const f of room.food) occupied.add(`${f.x},${f.y}`);
  for (let attempt = 0; attempt < 200; attempt++) {
    const x = Math.floor(Math.random() * (COLS - 6)) + 3;
    const y = Math.floor(Math.random() * (ROWS - 6)) + 3;
    const dirs = [{ x: 1, y: 0 }, { x: -1, y: 0 }, { x: 0, y: 1 }, { x: 0, y: -1 }];
    const d = dirs[Math.floor(Math.random() * dirs.length)];
    const cells = [];
    let ok = true;
    for (let i = 0; i < 3; i++) {
      const cx = x - d.x * i;
      const cy = y - d.y * i;
      if (occupied.has(`${cx},${cy}`)) { ok = false; break; }
      cells.push({ x: cx, y: cy });
    }
    if (ok) return { snake: cells, dir: d };
  }
  return { snake: [{ x: 3, y: 3 }, { x: 2, y: 3 }, { x: 1, y: 3 }], dir: { x: 1, y: 0 } };
}

function collectOccupied(room) {
  const occupied = new Set();
  for (const p of room.players.values()) {
    if (p.alive) for (const s of p.snake) occupied.add(`${s.x},${s.y}`);
  }
  for (const f of room.food) occupied.add(`${f.x},${f.y}`);
  for (const g of room.goldFood) occupied.add(`${g.x},${g.y}`);
  return occupied;
}

function placeFood(room) {
  const occupied = collectOccupied(room);
  for (let attempt = 0; attempt < 300; attempt++) {
    const x = Math.floor(Math.random() * COLS);
    const y = Math.floor(Math.random() * ROWS);
    if (!occupied.has(`${x},${y}`)) {
      room.food.push({ x, y });
      return;
    }
  }
}

function fillFood(room) {
  while (room.food.length < FOOD_COUNT) placeFood(room);
}

function placeGoldFood(room) {
  if (room.state !== 'playing') return;
  const occupied = collectOccupied(room);
  for (let attempt = 0; attempt < 300; attempt++) {
    const x = Math.floor(Math.random() * COLS);
    const y = Math.floor(Math.random() * ROWS);
    if (!occupied.has(`${x},${y}`)) {
      room.goldFood.push({ x, y });
      broadcastState(room);
      return;
    }
  }
}

function spawnPlayer(room, player) {
  const spawn = spawnPos(room);
  player.snake = spawn.snake;
  player.dir = spawn.dir;
  player.nextDir = spawn.dir;
  player.alive = true;
  player.score = 0;
  player.respawnTimer = null;
}

function tick(room) {
  for (const player of room.players.values()) {
    if (!player.alive) continue;

    player.dir = player.nextDir;
    const head = {
      x: (player.snake[0].x + player.dir.x + COLS) % COLS,
      y: (player.snake[0].y + player.dir.y + ROWS) % ROWS,
    };

    let hitSelf = false;
    for (const s of player.snake) {
      if (s.x === head.x && s.y === head.y) { hitSelf = true; break; }
    }
    if (hitSelf) { killPlayer(room, player); continue; }

    let hitOther = false;
    for (const other of room.players.values()) {
      if (other.id === player.id || !other.alive) continue;
      for (const s of other.snake) {
        if (s.x === head.x && s.y === head.y) { hitOther = true; break; }
      }
      if (hitOther) break;
    }
    if (hitOther) { killPlayer(room, player); continue; }

    player.snake.unshift(head);

    let grew = false;
    for (let i = 0; i < room.goldFood.length; i++) {
      if (room.goldFood[i].x === head.x && room.goldFood[i].y === head.y) {
        room.goldFood.splice(i, 1);
        player.score += GOLD_POINTS;
        grew = true;
        break;
      }
    }
    if (!grew) {
      for (let i = 0; i < room.food.length; i++) {
        if (room.food[i].x === head.x && room.food[i].y === head.y) {
          room.food.splice(i, 1);
          player.score += 1;
          grew = true;
          break;
        }
      }
    }
    if (!grew) player.snake.pop();
  }

  fillFood(room);

  let winner = null;
  for (const p of room.players.values()) {
    if (p.score >= WIN_SCORE && (!winner || p.score > winner.score)) {
      winner = p;
    }
  }
  if (winner) {
    endGame(room, winner);
    return;
  }

  broadcastState(room);
}

function endGame(room, winner) {
  room.state = 'finished';
  clearInterval(room.tickInterval);
  clearInterval(room.goldInterval);
  room.tickInterval = null;
  room.goldInterval = null;
  room.winner = {
    id: winner.id,
    name: winner.name,
    color: winner.color,
    score: winner.score,
  };
  for (const p of room.players.values()) {
    if (p.respawnTimer) { clearTimeout(p.respawnTimer); p.respawnTimer = null; }
  }
  broadcastState(room);
}

function killPlayer(room, player) {
  player.alive = false;
  player.snake = [];
  player.respawnTimer = setTimeout(() => {
    if (room.state !== 'playing') return;
    if (!room.players.has(player.id)) return;
    spawnPlayer(room, player);
    broadcastState(room);
  }, RESPAWN_DELAY_MS);
}

function broadcastState(room) {
  const players = [];
  for (const p of room.players.values()) {
    players.push({
      id: p.id,
      name: p.name,
      color: p.color,
      snake: p.snake,
      dir: p.dir,
      alive: p.alive,
      score: p.score,
    });
  }
  const msg = JSON.stringify({
    type: 'state',
    players,
    food: room.food,
    goldFood: room.goldFood,
    cols: COLS,
    rows: ROWS,
    roomName: room.roomName,
    winner: room.winner,
    state: room.state,
    winScore: WIN_SCORE,
  });
  for (const p of room.players.values()) {
    if (p.ws.readyState === 1) p.ws.send(msg);
  }
}

function broadcastLobby(room) {
  const players = [];
  for (const p of room.players.values()) {
    players.push({ id: p.id, name: p.name, color: p.color });
  }
  const ready = room.players.size >= room.maxPlayers;
  const msg = JSON.stringify({
    type: 'lobby',
    players,
    code: room.code,
    roomName: room.roomName,
    maxPlayers: room.maxPlayers,
    hostId: room.hostId,
    ready,
  });
  for (const p of room.players.values()) {
    if (p.ws.readyState === 1) p.ws.send(msg);
  }
}

function startGame(room) {
  if (room.state === 'playing') return;
  clearInterval(room.tickInterval);
  clearInterval(room.goldInterval);
  room.state = 'playing';
  room.food = [];
  room.goldFood = [];
  room.winner = null;
  for (const p of room.players.values()) {
    if (p.respawnTimer) { clearTimeout(p.respawnTimer); p.respawnTimer = null; }
  }
  fillFood(room);
  for (const p of room.players.values()) spawnPlayer(room, p);
  room.tickInterval = setInterval(() => tick(room), TICK_MS);
  room.goldInterval = setInterval(() => placeGoldFood(room), GOLD_INTERVAL_MS);
  broadcastState(room);
}

function removePlayer(room, playerId) {
  const player = room.players.get(playerId);
  if (player && player.respawnTimer) clearTimeout(player.respawnTimer);
  room.players.delete(playerId);
  if (room.players.size === 0) {
    destroyRoom(room.code);
  } else {
    if (room.hostId === playerId) {
      room.hostId = room.players.keys().next().value;
    }
    if (room.state === 'lobby') broadcastLobby(room);
    else broadcastState(room);
  }
}

// HTTP server
const server = http.createServer((req, res) => {
  let filePath;
  if (req.url === '/' || req.url === '/index.html') {
    filePath = path.join(__dirname, 'public', 'index.html');
  } else {
    filePath = path.join(__dirname, 'public', req.url);
  }

  const ext = path.extname(filePath);
  const mimeTypes = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
  };

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'text/plain' });
    res.end(data);
  });
});

// WebSocket
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  let currentRoom = null;
  let playerId = null;

  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    if (msg.type === 'create') {
      const code = genRoomCode();
      const roomName = (msg.roomName || 'Room').slice(0, 32);
      const maxPlayers = Math.max(2, Math.min(8, parseInt(msg.maxPlayers) || 2));
      const room = createRoom(code, roomName, maxPlayers);
      currentRoom = room;
      playerId = room.nextPlayerId++;
      room.hostId = playerId;
      const colorIdx = (playerId - 1) % COLORS.length;
      room.players.set(playerId, {
        id: playerId,
        ws,
        name: (msg.name || 'Player').slice(0, 16),
        color: COLORS[colorIdx],
        snake: [],
        dir: { x: 1, y: 0 },
        nextDir: { x: 1, y: 0 },
        alive: false,
        score: 0,
        respawnTimer: null,
      });
      ws.send(JSON.stringify({ type: 'joined', code, playerId }));
      broadcastLobby(room);
    }

    else if (msg.type === 'join') {
      const code = (msg.code || '').toUpperCase().trim();
      const room = rooms.get(code);
      if (!room) {
        ws.send(JSON.stringify({ type: 'error', message: 'Room not found' }));
        return;
      }
      if (room.players.size >= room.maxPlayers) {
        ws.send(JSON.stringify({ type: 'error', message: `Room is full (${room.maxPlayers}/${room.maxPlayers})` }));
        return;
      }
      currentRoom = room;
      playerId = room.nextPlayerId++;
      const colorIdx = (playerId - 1) % COLORS.length;
      const player = {
        id: playerId,
        ws,
        name: (msg.name || 'Player').slice(0, 16),
        color: COLORS[colorIdx],
        snake: [],
        dir: { x: 1, y: 0 },
        nextDir: { x: 1, y: 0 },
        alive: false,
        score: 0,
        respawnTimer: null,
      };
      room.players.set(playerId, player);
      ws.send(JSON.stringify({ type: 'joined', code, playerId }));
      if (room.state === 'playing') {
        spawnPlayer(room, player);
        broadcastState(room);
      } else if (room.state === 'finished') {
        broadcastState(room);
      } else {
        broadcastLobby(room);
      }
    }

    else if (msg.type === 'start') {
      if (!currentRoom) return;
      if (playerId !== currentRoom.hostId) return;
      if (currentRoom.state === 'playing') return;
      if (currentRoom.state === 'lobby' && currentRoom.players.size < currentRoom.maxPlayers) return;
      startGame(currentRoom);
    }

    else if (msg.type === 'dir') {
      if (!currentRoom) return;
      const player = currentRoom.players.get(playerId);
      if (!player || !player.alive) return;
      const nx = msg.x;
      const ny = msg.y;
      if (Math.abs(nx) + Math.abs(ny) !== 1) return;
      if (player.snake.length > 1 && nx === -player.dir.x && ny === -player.dir.y) return;
      player.nextDir = { x: nx, y: ny };
    }
  });

  ws.on('close', () => {
    if (currentRoom && playerId != null) {
      removePlayer(currentRoom, playerId);
    }
  });
});

server.listen(PORT, () => {
  console.log(`Snake server running on http://localhost:${PORT}`);
});
