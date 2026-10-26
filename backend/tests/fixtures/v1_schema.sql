CREATE TABLE games (
	id VARCHAR(36) NOT NULL, 
	pgn TEXT NOT NULL, 
	user_color VARCHAR(5) NOT NULL, 
	elo INTEGER NOT NULL, 
	playstyle TEXT, 
	headers JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE engine_results (
	id INTEGER NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	ply INTEGER, 
	fen VARCHAR(100) NOT NULL, 
	tier VARCHAR(6) NOT NULL, 
	depth INTEGER NOT NULL, 
	time_ms INTEGER NOT NULL, 
	lines JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (game_id, fen, tier), 
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE INDEX ix_engine_results_game_id ON engine_results (game_id);
CREATE TABLE game_summaries (
	game_id VARCHAR(36) NOT NULL, 
	summary JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (game_id), 
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE TABLE chat_messages (
	id INTEGER NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	role VARCHAR(10) NOT NULL, 
	content JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE INDEX ix_chat_messages_game_id ON chat_messages (game_id);
CREATE TABLE llm_usage (
	id INTEGER NOT NULL, 
	game_id VARCHAR(36), 
	endpoint VARCHAR(32) NOT NULL, 
	model VARCHAR(64) NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	cache_read_tokens INTEGER NOT NULL, 
	cache_write_tokens INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE INDEX ix_llm_usage_game_id ON llm_usage (game_id);
CREATE TABLE pending_tool_calls (
	request_id VARCHAR(36) NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	tool_use JSON NOT NULL, 
	positions JSON NOT NULL, 
	extra_results JSON NOT NULL, 
	tool_calls_used INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (request_id), 
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE INDEX ix_pending_tool_calls_game_id ON pending_tool_calls (game_id);
