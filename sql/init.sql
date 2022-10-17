create table if not exists public."user"
(
	discord_id bigint not null
		primary key,
	username varchar
);

alter table public."user" owner to postgres;

create table if not exists public.game
(
	twitch_id integer not null
		primary key,
	name varchar not null,
	image_url varchar not null
);

alter table public.game owner to postgres;

create table if not exists public.streamer
(
	twitch_id integer not null
		primary key,
	name varchar not null
);

alter table public.streamer owner to postgres;

create table if not exists public.association
(
	user_id bigint not null
		references public."user",
	game_id integer not null
		references public.game,
	streamer_id integer not null
		references public.streamer,
	created_at timestamp with time zone not null,
	primary key (user_id, game_id, streamer_id)
);

alter table public.association owner to postgres;

create table if not exists public.last_time_played
(
	streamer_id integer not null
		references public.streamer,
	game_id integer not null,
	last_played timestamp with time zone not null,
	primary key (streamer_id, game_id)
);

alter table public.last_time_played owner to postgres;

-- insert streamer Felps
insert into public.streamer (twitch_id, name) values (30672329, 'Felps');