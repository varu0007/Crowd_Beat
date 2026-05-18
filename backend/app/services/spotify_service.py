"""
spotify_service.py - Spotify Web API wrapper
Token exchange, user top tracks, audio features, genre-based search.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from app.config import get_settings


def _get_oauth_manager() -> SpotifyOAuth:
    """Create SpotifyOAuth manager (Authorization Code Flow, not PKCE)."""
    settings = get_settings()
    return SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope="user-top-read user-library-read playlist-read-private playlist-read-collaborative",
        show_dialog=True,
        open_browser=False,
    )


def get_authorize_url(session_id: str) -> str:
    """
    Generate Spotify authorization URL with session_id as state.
    """
    oauth = _get_oauth_manager()
    return oauth.get_authorize_url(state=session_id)


async def exchange_token(code: str) -> dict:
    """
    Exchange authorization code for access_token.
    """
    oauth = _get_oauth_manager()
    # spotipy get_access_token is sync, run in thread pool
    loop = asyncio.get_event_loop()
    token_info = await loop.run_in_executor(
        None, lambda: oauth.get_access_token(code, as_dict=True, check_cache=False)
    )
    return {
        "access_token": token_info["access_token"],
        "refresh_token": token_info.get("refresh_token", ""),
        "expires_in": token_info.get("expires_in", 3600),
        "expires_at": datetime.now(timezone.utc) + timedelta(
            seconds=token_info.get("expires_in", 3600)
        ),
    }


async def get_current_user(access_token: str) -> dict:
    """
    Get current user info.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()
    user = await loop.run_in_executor(None, sp.current_user)
    return {
        "spotify_user_id": user.get("id", ""),
        "display_name": user.get("display_name", ""),
    }


async def get_user_top_tracks(
    access_token: str,
    limit: int = 50,
    time_range: str = "medium_term",
) -> list[dict]:
    """
    Get user top tracks.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None,
        lambda: sp.current_user_top_tracks(limit=limit, time_range=time_range),
    )

    tracks = []
    for item in results.get("items", []):
        tracks.append({
            "spotify_track_id": item["id"],
            "track_name": item.get("name", "Unknown"),
            "artist_name": ", ".join(a["name"] for a in item.get("artists", [])),
            "popularity": item.get("popularity", 0),
        })
    return tracks


async def get_audio_features_batch(
    access_token: str,
    track_ids: list[str],
) -> dict[str, dict]:
    """Fetch audio features in batches of up to 100 IDs."""
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()
    features_map: dict[str, dict] = {}
    batch_size = 100

    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i : i + batch_size]
        try:
            results = await loop.run_in_executor(
                None, lambda b=batch: sp.audio_features(tracks=b)
            )
            if results:
                for af in results:
                    if af and af.get("id"):
                        features_map[af["id"]] = {
                            "danceability": af.get("danceability"),
                            "energy": af.get("energy"),
                            "valence": af.get("valence"),
                            "tempo": af.get("tempo"),
                            "acousticness": af.get("acousticness"),
                            "instrumentalness": af.get("instrumentalness"),
                        }
        except Exception as e:
            # Audio Features API may be deprecated or forbidden; skip silently
            print(f"[spotify_service] audio_features error: {e}")
            continue

        # Rate limit guard
        if i + batch_size < len(track_ids):
            await asyncio.sleep(0.1)

    return features_map


_GENRE_ARTISTS: dict[str, list[str]] = {
    "k-pop": [
        "BTS", "BLACKPINK", "aespa", "NewJeans", "IVE", "Stray Kids", "TWICE", "ITZY",
        "ENHYPEN", "TOMORROW X TOGETHER", "EXO", "SHINee", "GOT7", "NCT 127", "NCT Dream",
        "Red Velvet", "Girls' Generation", "MAMAMOO", "SISTAR", "4Minute",
        "2NE1", "BIGBANG", "MONSTA X", "ASTRO", "VICTON", "PENTAGON", "THE BOYZ",
        "AB6IX", "Golden Child", "BTOB", "VIXX", "Block B",
        "SEVENTEEN", "DAY6", "N.Flying", "ONEWE",
        "LE SSERAFIM", "KISS OF LIFE", "tripleS", "(G)I-DLE", "Kep1er",
        "NMIXX", "fromis_9", "Weeekly", "LOONA", "Dreamcatcher",
    ],
    "pop": [
        "Taylor Swift", "Dua Lipa", "The Weeknd", "Olivia Rodrigo", "Harry Styles",
        "Ariana Grande", "Ed Sheeran", "Billie Eilish", "Justin Bieber", "Lady Gaga",
        "Katy Perry", "Selena Gomez", "Shawn Mendes", "Camila Cabello", "Charlie Puth",
        "Lizzo", "Doja Cat", "Lana Del Rey", "Halsey", "Bebe Rexha",
        "Cardi B", "Nicki Minaj", "Meghan Trainor", "Sia", "Ava Max",
        "Sam Smith", "Adele", "P!nk", "Miley Cyrus", "Christina Aguilera",
        "Maroon 5", "OneRepublic", "Imagine Dragons", "Coldplay", "Troye Sivan",
        "Lauv", "Conan Gray", "girl in red", "gracie abrams", "Stephen Sanchez",
        "Sabrina Carpenter", "Chappell Roan", "Tate McRae", "Zara Larsson", "FLETCHER",
        "Rema", "Khalid", "H.E.R.", "SZA", "Summer Walker",
    ],
    "hip-hop": [
        "Drake", "Travis Scott", "Kendrick Lamar", "Post Malone", "J. Cole",
        "21 Savage", "Future", "Lil Baby", "Gunna", "Young Thug",
        "Nicki Minaj", "Cardi B", "Megan Thee Stallion", "Doja Cat", "City Girls",
        "A$AP Rocky", "Tyler the Creator", "Childish Gambino", "Joey Bada$$", "JID",
        "Denzel Curry", "Rico Nasty", "Doja Cat", "Doechii", "GloRilla",
        "Jack Harlow", "Polo G", "Rod Wave", "Lil Durk", "Lil Uzi Vert",
        "Playboi Carti", "NAV", "Don Toliver", "Yeat", "Destroy Lonely",
        "Ski Mask the Slump God", "Juice WRLD", "Pop Smoke", "NBA YoungBoy", "NLE Choppa",
        "42 Dugg", "EST Gee", "Moneybagg Yo", "Mozzy", "Benny the Butcher",
        "Westside Gunn", "Conway the Machine", "Boldy James", "Flee Lord", "Ransom",
    ],
    "r-n-b": [
        "The Weeknd", "SZA", "Bruno Mars", "H.E.R.", "Summer Walker",
        "Giveon", "Brent Faiyaz", "Daniel Caesar", "Frank Ocean", "Miguel",
        "Jhene Aiko", "Kehlani", "Lucky Daye", "Kiana Lede", "Snoh Aalegra",
        "Ari Lennox", "Ella Mai", "Normani", "Tinashe", "Tink",
        "6LACK", "PJ Morton", "Leon Bridges", "Gary Clark Jr.", "Anderson Paak",
        "Silk Sonic", "Alicia Keys", "John Legend", "Ne-Yo", "Usher",
        "Chris Brown", "Trey Songz", "Tyrese", "Tank", "Fantasia",
        "Jazmine Sullivan", "Mary J. Blige", "Erykah Badu", "Jill Scott", "Lauryn Hill",
        "Beyonce", "Rihanna", "Mariah Carey", "Janet Jackson", "Whitney Houston",
        "Maxwell", "D'Angelo", "Musiq Soulchild", "Anthony Hamilton", "Charlie Wilson",
    ],
    "electronic": [
        "Calvin Harris", "Marshmello", "Martin Garrix", "Flume", "Deadmau5",
        "Skrillex", "Diplo", "Zedd", "Kygo", "Illenium",
        "Odesza", "Petit Biscuit", "San Holo", "Slushii", "Gryffin",
        "Madeon", "Porter Robinson", "Virtual Self", "Rustie", "Arca",
        "Four Tet", "Burial", "Aphex Twin", "Boards of Canada", "Autechre",
        "Nicolas Jaar", "DJ Shadow", "Flying Lotus", "Thundercat", "BadBadNotGood",
        "Jamie xx", "Mount Kimbie", "Caribou", "Tycho", "Com Truise",
        "Bonobo", "Catching Flies", "Tourist", "Kllo", "Bicep",
        "Fred again", "Mall Grab", "Avalon Emerson", "Objekt", "rRoxymore",
        "Anz", "DJ Stingray", "Actress", "Blanck Mass", "Lee Gamble",
    ],
    "house": [
        "David Guetta", "Disclosure", "Fisher", "Kaytranada", "Duke Dumont",
        "Tchami", "Malaa", "DJ Snake", "Robin Schulz", "Felix Jaehn",
        "Oliver Heldens", "Kungs", "Sam Feldt", "Deepend", "Lost Frequencies",
        "Kygo", "Alle Farben", "Nora En Pure", "CamelPhat", "Solardo",
        "Hot Since 82", "Patrick Topping", "Green Velvet", "Lee Foss", "Justin Martin",
        "Richy Ahmed", "Hannah Wants", "Maya Jane Coles", "Kerri Chandler", "Larry Heard",
        "Frankie Knuckles", "Larry Levan", "Ron Hardy", "Marshall Jefferson", "Jamie Principle",
        "Todd Terry", "Masters at Work", "Louie Vega", "Kenny Dope", "Roger Sanchez",
        "Defected Records", "Glitterbox", "Toolroom", "Dirtybird", "Crosstown Rebels",
        "MK", "Claptone", "Andhim", "&ME", "Rampa",
    ],
    "techno": [
        "Carl Cox", "Charlotte de Witte", "Richie Hawtin", "Amelie Lens", "Adam Beyer",
        "Sven Vath", "Chris Liebing", "Dave Clarke", "Ben Klock", "Marcel Dettmann",
        "DVS1", "Blawan", "Surgeon", "Ancient Methods", "Phase",
        "Alignment", "SPFDJ", "Rebekah", "Paula Temple", "Volruptus",
        "Soma Records", "Drumcode", "Berghain", "Tresor", "Warp Records",
        "Phuture", "Model 500", "Juan Atkins", "Kevin Saunderson", "Derrick May",
        "Jeff Mills", "Robert Hood", "Underground Resistance", "Mike Banks", "Drexciya",
        "Surgeon", "Regis", "Female", "Shifted", "Orphx",
        "Phase Fatale", "Alignment", "Ron Morelli", "Headless Horseman", "Stanislav Tolkachev",
        "Truncate", "Exium", "Planetary Assault Systems", "Perc", "Answer Code Request",
    ],
    "trance": [
        "Armin van Buuren", "Above & Beyond", "Tiesto", "Paul van Dyk", "Ferry Corsten",
        "ATB", "Markus Schulz", "Aly & Fila", "Cosmic Gate", "John O Callaghan",
        "Bryan Kearney", "Giuseppe Ottaviani", "Myon & Shane 54", "Simon Patterson", "Dan Stone",
        "Andrew Rayel", "Ilan Bluestone", "Kyau & Albert", "Lange", "Dash Berlin",
        "Solarstone", "Rank 1", "Lost Witness", "BT", "Maor Levi",
        "Protoculture", "ReOrder", "Roger Shah", "Tritonal", "W&W",
        "Infected Mushroom", "Astrix", "Vini Vici", "Ace Ventura", "Rinkadink",
        "Seven Lions", "kill:sector", "Neelix", "Emok", "Banel",
        "KhoMha", "M.I.K.E.", "Factor B", "Craig Connelly", "Jordan Suckley",
        "Heatbeat", "Omnia", "Alexander Popov", "Bjorn Akesson", "Sunlounger",
    ],
    "dubstep": [
        "Skrillex", "Excision", "Knife Party", "Virtual Riot", "Flux Pavilion",
        "Zomboy", "Datsik", "Borgore", "Doctor P", "Kill the Noise",
        "Getter", "Subtronics", "Gutter Garv", "Liquid Stranger", "Space Laces",
        "Barely Alive", "Eptic", "Wooli", "Svdden Death", "Rezz",
        "12th Planet", "Downlink", "Funtcase", "Crissy Criss", "Hizzlegood",
        "Benga", "Skream", "Digital Mystikz", "Mala", "Coki",
        "Rusko", "Caspa", "Bar 9", "N-Type", "Truth",
        "Loefah", "Pinch", "Headhunter", "Hatcha", "Youngsta",
        "Chase & Status", "Nero", "Example", "Sub Focus", "Wilkinson",
        "Pendulum", "Noisia", "The Qemists", "Spor", "Black Sun Empire",
    ],
    "dance": [
        "Calvin Harris", "Dua Lipa", "David Guetta", "Kygo", "Clean Bandit",
        "Avicii", "Zedd", "Martin Garrix", "Tiesto", "Marshmello",
        "Charli XCX", "Ava Max", "Zara Larsson", "Bebe Rexha", "Meghan Trainor",
        "Carly Rae Jepsen", "Katy Perry", "Ariana Grande", "Selena Gomez", "Doja Cat",
        "Jason Derulo", "Flo Rida", "Pitbull", "will.i.am", "Black Eyed Peas",
        "LMFAO", "Kesha", "Ke$ha", "Far East Movement", "Iyaz",
        "Sigala", "Jonas Blue", "Jax Jones", "MK", "Gorgon City",
        "Shift K3Y", "Route 94", "Hannah Wants", "Chloe Howl", "AlunaGeorge",
        "Rudimental", "Disclosure", "Basement Jaxx", "Faithless", "Moloko",
        "Daft Punk", "Justice", "Cassius", "SebastiAn", "Kavinsky",
    ],
    "disco": [
        "Daft Punk", "Donna Summer", "ABBA", "Nile Rodgers", "Giorgio Moroder",
        "Chic", "Sister Sledge", "Diana Ross", "The Bee Gees", "KC and the Sunshine Band",
        "Gloria Gaynor", "Village People", "Earth Wind & Fire", "Kool & the Gang", "George McCrae",
        "Cerrone", "Patrick Hernandez", "Boney M", "Ottawan", "Sheila E",
        "Rick James", "Cameo", "Gap Band", "Zapp", "Roger",
        "Shalamar", "Dynasty", "Lakeside", "Midnight Star", "Aurra",
        "Sylvester", "Two Tons of Fun", "Martha Wash", "Jocelyn Brown", "Carol Williams",
        "Alicia Bridges", "Amanda Lear", "Gino Soccio", "Jean Carn", "Musique",
        "Tom Moulton", "Larry Levan", "Frankie Knuckles", "Ron Hardy", "Marshall Jefferson",
        "Todd Terry", "Kerri Chandler", "Masters at Work", "Louie Vega", "David Morales",
    ],
    "synth-pop": [
        "The Weeknd", "Tame Impala", "M83", "CHVRCHES", "Glass Animals",
        "Depeche Mode", "New Order", "Pet Shop Boys", "Erasure", "Yazoo",
        "Soft Cell", "Human League", "Ultravox", "Gary Numan", "Howard Jones",
        "Tears for Fears", "Simple Minds", "OMD", "Heaven 17", "ABC",
        "Duran Duran", "A-ha", "Alphaville", "Eurythmics", "Visage",
        "Grimes", "Chromatics", "TR/ST", "Cold Cave", "Lebanon Hanover",
        "Boy Harsher", "Molchat Doma", "She Wants Revenge", "White Lies", "Editors",
        "Hurts", "Ladytron", "Client", "Freezepop", "Aesthetic Perfection",
        "Perturbator", "Carpenter Brut", "Gunship", "Kavinsky", "Makeup and Vanity Set",
        "Com Truise", "Neon Indian", "Washed Out", "How to Dress Well", "Active Child",
    ],
    "rock": [
        "Foo Fighters", "The Black Keys", "Arctic Monkeys", "Jack White", "Queens of the Stone Age",
        "Muse", "Radiohead", "Blur", "Oasis", "The Verve",
        "The Rolling Stones", "The Beatles", "Led Zeppelin", "Pink Floyd", "The Who",
        "Fleetwood Mac", "Eagles", "Tom Petty", "Bruce Springsteen", "Bob Seger",
        "U2", "R.E.M.", "The Cure", "The Smiths", "The Pixies",
        "Sonic Youth", "Pavement", "Built to Spill", "Guided by Voices", "Sebadoh",
        "Beck", "Weezer", "Smashing Pumpkins", "Cake", "Modest Mouse",
        "Death Cab for Cutie", "Bright Eyes", "The National", "Interpol", "Editors",
        "Franz Ferdinand", "Kaiser Chiefs", "The Libertines", "Razorlight", "Kasabian",
        "The Killers", "Panic at the Disco", "Fall Out Boy", "My Chemical Romance", "30 Seconds to Mars",
    ],
    "hard-rock": [
        "AC/DC", "Guns N Roses", "Aerosmith", "Led Zeppelin", "Van Halen",
        "Def Leppard", "Bon Jovi", "Whitesnake", "Motley Crue", "Poison",
        "Twisted Sister", "Warrant", "Dokken", "Ratt", "Cinderella",
        "KISS", "Alice Cooper", "Ozzy Osbourne", "Black Sabbath", "Deep Purple",
        "Dio", "Rainbow", "Judas Priest", "Iron Maiden", "Scorpions",
        "Accept", "Saxon", "Motorhead", "Thin Lizzy", "UFO",
        "Foreigner", "Heart", "Pat Benatar", "Joan Jett", "Lita Ford",
        "Halestorm", "The Pretty Reckless", "Evanescence", "Paramore", "Skillet",
        "Shinedown", "Seether", "Breaking Benjamin", "Three Days Grace", "Hinder",
        "Theory of a Deadman", "Nickelback", "Puddle of Mudd", "Saliva", "Default",
    ],
    "metal": [
        "Metallica", "Gojira", "Spiritbox", "Sleep Token", "Bring Me The Horizon",
        "Trivium", "Lamb of God", "Pantera", "Slayer", "Megadeth",
        "Anthrax", "Testament", "Exodus", "Overkill", "Annihilator",
        "Death", "Morbid Angel", "Cannibal Corpse", "Obituary", "Deicide",
        "Darkthrone", "Mayhem", "Burzum", "Emperor", "Immortal",
        "Dimmu Borgir", "Cradle of Filth", "Behemoth", "Watain", "Dark Funeral",
        "Opeth", "Mastodon", "Tool", "Korn", "Deftones",
        "System of a Down", "Rage Against the Machine", "Slipknot", "Mudvayne", "Disturbed",
        "Machine Head", "Arch Enemy", "In Flames", "Soilwork", "Dark Tranquillity",
        "Amon Amarth", "Enslaved", "Moonsorrow", "Wintersun", "Children of Bodom",
    ],
    "punk": [
        "Green Day", "The Offspring", "Sum 41", "Blink-182", "Rancid",
        "NOFX", "Bad Religion", "Pennywise", "Lagwagon", "No Use for a Name",
        "The Ramones", "Sex Pistols", "The Clash", "The Damned", "Buzzcocks",
        "Wire", "Gang of Four", "The Jam", "Stiff Little Fingers", "Undertones",
        "Dead Kennedys", "Black Flag", "Circle Jerks", "Fear", "Germs",
        "Husker Du", "The Replacements", "Meat Puppets", "Descendents", "Minutemen",
        "Alkaline Trio", "Anti-Flag", "Rise Against", "The Bouncing Souls", "Hot Water Music",
        "Dropkick Murphys", "Flogging Molly", "The Real McKenzies", "Street Dogs", "Flatfoot 56",
        "Against Me!", "The Gaslight Anthem", "Social Distortion", "Stiff Little Fingers", "Bad Brains",
        "Propagandhi", "Strike Anywhere", "The Lawrence Arms", "Leatherface", "Jawbreaker",
    ],
    "grunge": [
        "Nirvana", "Pearl Jam", "Soundgarden", "Alice in Chains", "Stone Temple Pilots",
        "Mudhoney", "Screaming Trees", "Melvins", "L7", "Hole",
        "Pixies", "Dinosaur Jr.", "Sonic Youth", "My Bloody Valentine", "Sebadoh",
        "Pavement", "Built to Spill", "Guided by Voices", "Archers of Loaf", "Superchunk",
        "Smashing Pumpkins", "Garbage", "Live", "Bush", "Candlebox",
        "Silverchair", "Collective Soul", "7 Mary 3", "Matchbox Twenty", "Creed",
        "Fuel", "Filter", "Stabbing Westward", "Gravity Kills", "God Lives Underwater",
        "Blind Melon", "Temple of the Dog", "Mad Season", "Layne Staley", "Andrew Wood",
        "Mark Lanegan", "Chris Cornell", "Eddie Vedder", "Kurt Cobain", "Scott Weiland",
        "Them Crooked Vultures", "Queens of the Stone Age", "Eagles of Death Metal", "Mondo Generator", "Kyuss",
    ],
    "indie": [
        "Arctic Monkeys", "Tame Impala", "The 1975", "Vampire Weekend", "Bon Iver",
        "Fleet Foxes", "Sufjan Stevens", "Joanna Newsom", "Iron & Wine", "Jose Gonzalez",
        "Devendra Banhart", "Beirut", "Of Montreal", "Animal Collective", "MGMT",
        "Grizzly Bear", "Beach House", "Real Estate", "Wild Nothing", "Washed Out",
        "Neon Indian", "Chillwave", "Toro y Moi", "Unknown Mortal Orchestra", "Mac DeMarco",
        "Alex G", "Car Seat Headrest", "Snail Mail", "Julien Baker", "Lucy Dacus",
        "Japanese Breakfast", "Hand Habits", "Lomelda", "Palehound", "Florist",
        "Big Thief", "Adrianne Lenker", "Angel Olsen", "Sharon Van Etten", "Waxahatchee",
        "Soccer Mommy", "Hovvdy", "Palm", "Nation of Language", "Dehd",
        "Wiki", "Ratboys", "Deeper", "Faye Webster", "Indigo De Souza",
    ],
    "jazz": [
        "Miles Davis", "John Coltrane", "Norah Jones", "Herbie Hancock", "Bill Evans",
        "Charlie Parker", "Thelonious Monk", "Dizzy Gillespie", "Louis Armstrong", "Duke Ellington",
        "Ella Fitzgerald", "Billie Holiday", "Sarah Vaughan", "Nat King Cole", "Frank Sinatra",
        "Dave Brubeck", "Oscar Peterson", "Ahmad Jamal", "McCoy Tyner", "Chick Corea",
        "Keith Jarrett", "Brad Mehldau", "Esbjorn Svensson Trio", "Gonzalo Rubalcaba", "Jacky Terrasson",
        "Pat Metheny", "John Scofield", "Bill Frisell", "Kurt Rosenwinkel", "Mike Stern",
        "Charles Mingus", "Ron Carter", "Paul Chambers", "Scott LaFaro", "Dave Holland",
        "Art Blakey", "Max Roach", "Roy Haynes", "Tony Williams", "Elvin Jones",
        "Wayne Shorter", "Joe Henderson", "Sonny Rollins", "Dexter Gordon", "Lee Morgan",
        "Kamasi Washington", "Thundercat", "BadBadNotGood", "Alfa Mist", "GoGo Penguin",
    ],
    "blues": [
        "B.B. King", "Gary Clark Jr.", "John Mayer", "Eric Clapton", "Stevie Ray Vaughan",
        "Muddy Waters", "Robert Johnson", "Howlin Wolf", "John Lee Hooker", "Buddy Guy",
        "Albert King", "Freddie King", "Magic Sam", "Otis Rush", "Junior Wells",
        "Paul Butterfield", "Michael Bloomfield", "Elvin Bishop", "Charlie Musselwhite", "James Cotton",
        "Joe Bonamassa", "Kenny Wayne Shepherd", "Walter Trout", "Jonny Lang", "Tab Benoit",
        "Keb Mo", "Taj Mahal", "Corey Harris", "Guy Davis", "Ben Harper",
        "Marcus King", "Tyler Bryant", "Ally Venable", "Vanessa Collier", "Samantha Fish",
        "Ana Popovic", "Devon Allman", "Luther Allison", "Lonnie Brooks", "Magic Slim",
        "Son House", "Skip James", "Charlie Patton", "Mississippi Fred McDowell", "Big Bill Broonzy",
        "T-Bone Walker", "Lowell Fulson", "Pee Wee Crayton", "Roy Brown", "Fats Domino",
    ],
    "soul": [
        "Alicia Keys", "John Legend", "Sam Smith", "Adele", "Amy Winehouse",
        "Aretha Franklin", "Otis Redding", "Ray Charles", "Marvin Gaye", "Stevie Wonder",
        "James Brown", "Al Green", "Curtis Mayfield", "Sam Cooke", "Solomon Burke",
        "Wilson Pickett", "Percy Sledge", "Clarence Carter", "Ben E. King", "Jackie Wilson",
        "Etta James", "Nina Simone", "Gladys Knight", "Patti LaBelle", "Dionne Warwick",
        "Whitney Houston", "Tina Turner", "Diana Ross", "Mary J. Blige", "Erykah Badu",
        "Jill Scott", "India Arie", "Musiq Soulchild", "Anthony Hamilton", "Kindred the Family Soul",
        "Leon Bridges", "Charles Bradley", "Lee Fields", "Sharon Jones", "St. Paul and the Broken Bones",
        "Anderson Paak", "PJ Morton", "Lucky Daye", "Ari Lennox", "Ella Mai",
        "Giveon", "Brent Faiyaz", "Daniel Caesar", "Jordan Ward", "Victoria Monet",
    ],
    "funk": [
        "Bruno Mars", "Anderson Paak", "Silk Sonic", "Jamiroquai", "Earth Wind & Fire",
        "James Brown", "George Clinton", "Parliament", "Funkadelic", "Sly Stone",
        "Kool & the Gang", "Ohio Players", "Cameo", "Con Funk Shun", "Bar-Kays",
        "Gap Band", "Zapp", "Roger", "Rick James", "Prince",
        "Maze featuring Frankie Beverly", "Slave", "Lakeside", "Midnight Star", "Dazz Band",
        "Tower of Power", "Average White Band", "Commodores", "Heatwave", "Rose Royce",
        "Rufus", "Chaka Khan", "Jocelyn Brown", "Cynthia", "Gwen McCrae",
        "Bootsy Collins", "Maceo Parker", "Fred Wesley", "Pee Wee Ellis", "Alfred James Ellis",
        "Nile Rodgers", "Chic", "Lenny White", "Harvey Mason", "Bill Summers",
        "Vulfpeck", "Cory Wong", "Jacob Collier", "Scary Pockets", "Pomplamoose",
    ],
    "country": [
        "Morgan Wallen", "Luke Combs", "Kacey Musgraves", "Chris Stapleton", "Zach Bryan",
        "Eric Church", "Jason Aldean", "Blake Shelton", "Keith Urban", "Brad Paisley",
        "Carrie Underwood", "Miranda Lambert", "Reba McEntire", "Dolly Parton", "Faith Hill",
        "Tim McGraw", "Garth Brooks", "George Strait", "Alan Jackson", "Vince Gill",
        "Kenny Chesney", "Dierks Bentley", "Thomas Rhett", "Cole Swindell", "Tyler Hubbard",
        "Florida Georgia Line", "Dan + Shay", "Old Dominion", "Midland", "Lanco",
        "Cody Johnson", "Cody Jinks", "Turnpike Troubadours", "Sturgill Simpson", "Jason Isbell",
        "Maren Morris", "Ashley McBryde", "Carly Pearce", "Tenille Townes", "Caylee Hammack",
        "Lainey Wilson", "Jelly Roll", "Bailey Zimmerman", "Nate Smith", "ERNEST",
        "Tyler Childers", "Colter Wall", "Charley Crockett", "Whitey Morgan", "Wayne Hancock",
    ],
    "acoustic": [
        "Passenger", "Ben Howard", "James Bay", "Vance Joy", "Hozier",
        "Ed Sheeran", "John Mayer", "Jack Johnson", "Jason Mraz", "Michael Buble",
        "Damien Rice", "David Gray", "Badly Drawn Boy", "James Blunt", "Snow Patrol",
        "Ray LaMontagne", "Gregory Alan Isakov", "Joshua Radin", "Angus & Julia Stone", "Missy Higgins",
        "Matt Corby", "Hollow Coves", "Novo Amor", "Aldous Harding", "Julia Jacklin",
        "Phoebe Bridgers", "Faye Webster", "Julien Baker", "Lucy Dacus", "Mitski",
        "Lana Del Rey", "Mazzy Star", "Hope Sandoval", "Cowboy Junkies", "Cat Power",
        "Iron & Wine", "Fleet Foxes", "Sufjan Stevens", "Bon Iver", "Perfume Genius",
        "Jose Gonzalez", "Jorge Drexler", "Nick Drake", "Tim Buckley", "John Martyn",
        "Bert Jansch", "Pentangle", "Fairport Convention", "Sandy Denny", "Richard Thompson",
    ],
    "ambient": [
        "Brian Eno", "Moby", "Jon Hopkins", "Nils Frahm", "Sigur Ros",
        "Stars of the Lid", "Tim Hecker", "William Basinski", "Loscil", "The Caretaker",
        "Klaus Schulze", "Tangerine Dream", "Jean-Michel Jarre", "Vangelis", "Harold Budd",
        "Max Richter", "Ola Gjeilo", "Jonn Serrie", "Steve Roach", "Robert Rich",
        "Lustmord", "Raison d Etre", "Trobar de Muides", "Dead Can Dance", "Vas",
        "Hammock", "Eluvium", "Helios", "Olan Mill", "Rafael Anton Irisarri",
        "Deaf Center", "Biosphere", "Aun", "Machinefabriek", "Chihei Hatakeyama",
        "Grouper", "Lawrence English", "David Tagg", "Windy & Carl", "Stars of the Lid",
        "Goldmund", "Peter Broderick", "Hauschka", "Olafur Arnalds", "Johann Johannsson",
        "Ryuichi Sakamoto", "Sakamoto", "Erik Satie", "Morton Feldman", "John Cage",
    ],
    "classical": [
        "Hans Zimmer", "Ludovico Einaudi", "Yo-Yo Ma", "Lang Lang", "Itzhak Perlman",
        "Hilary Hahn", "Joshua Bell", "Maxim Vengerov", "Janine Jansen", "Ray Chen",
        "Martha Argerich", "Evgeny Kissin", "Vladimir Horowitz", "Glenn Gould", "Arthur Rubinstein",
        "Khatia Buniatishvili", "Daniil Trifonov", "Yuja Wang", "Alice Sara Ott", "Behzod Abduraimov",
        "Placido Domingo", "Luciano Pavarotti", "Jose Carreras", "Andrea Bocelli", "Bryn Terfel",
        "Cecilia Bartoli", "Renee Fleming", "Anna Netrebko", "Diana Damrau", "Joyce DiDonato",
        "Ennio Morricone", "John Williams", "Bernard Herrmann", "Jerry Goldsmith", "Max Steiner",
        "Philip Glass", "Steve Reich", "John Adams", "Arvo Part", "Sofia Gubaidulina",
        "Max Richter", "Nils Frahm", "Johann Johannsson", "Ennio Morricone", "Olafur Arnalds",
        "Bach", "Beethoven", "Mozart", "Chopin", "Schubert",
    ],
    "reggae": [
        "Bob Marley", "Sean Paul", "Damian Marley", "Chronixx", "Protoje",
        "Ziggy Marley", "Stephen Marley", "Ky-Mani Marley", "Julian Marley", "Bunny Wailer",
        "Peter Tosh", "Jimmy Cliff", "Toots and the Maytals", "The Wailers", "Culture",
        "Burning Spear", "Steel Pulse", "Lucky Dube", "Alpha Blondy", "Tiken Jah Fakoly",
        "Sizzla", "Capleton", "Buju Banton", "Beenie Man", "Bounty Killer",
        "Vybz Kartel", "Popcaan", "Alkaline", "Mavado", "I-Octane",
        "Koffee", "Jah9", "Sade Moxey", "Etana", "Tarrus Riley",
        "Romain Virgo", "Christopher Martin", "Busy Signal", "Richie Spice", "Pressure",
        "Midnite", "Anthony B", "Turbulence", "Luciano", "Bushman",
        "Junior Kelly", "Queen Ifrica", "Freddie McGregor", "Dennis Brown", "Gregory Isaacs",
    ],
    "latin": [
        "Bad Bunny", "J Balvin", "Maluma", "Ozuna", "Rauw Alejandro",
        "Daddy Yankee", "Nicky Jam", "Farruko", "Anuel AA", "Jhay Cortez",
        "Karol G", "Becky G", "Natti Natasha", "Anitta", "Rosalia",
        "Shakira", "Jennifer Lopez", "Marc Anthony", "Victor Manuelle", "Gilberto Santa Rosa",
        "Romeo Santos", "Prince Royce", "Aventura", "Grupo Extra", "Limite",
        "Enrique Iglesias", "Luis Miguel", "Alejandro Fernandez", "Juan Gabriel", "Marco Antonio Solis",
        "Gloria Estefan", "Celia Cruz", "Hector Lavoe", "Willie Colon", "Ruben Blades",
        "Carlos Santana", "Selena", "Tito Puente", "Mongo Santamaria", "Ibrahim Ferrer",
        "Pitbull", "CNCO", "Reik", "Ha-Ash", "Carlos Rivera",
        "Sebastian Yatra", "Camilo", "Kali Uchis", "Jessie Reyez", "Carla Morrison",
    ],
    "salsa": [
        "Marc Anthony", "Celia Cruz", "Hector Lavoe", "Victor Manuelle", "Gilberto Santa Rosa",
        "Willie Colon", "Ruben Blades", "Johnny Pacheco", "Cuco Valoy", "Johnny Ventura",
        "El Gran Combo", "Los Van Van", "Oscar De Leon", "Ismael Rivera", "Cheo Feliciano",
        "Bobby Cruz", "Ricardo Ray", "Pete El Conde Rodriguez", "Tito Rodriguez", "Tito Puente",
        "Eddie Palmieri", "Ray Barretto", "Larry Harlow", "Mongo Santamaria", "Patato Valdes",
        "La India", "Albita", "Olga Tanon", "Brenda K. Starr", "Myriam Hernandez",
        "Carlos Puebla", "Beny More", "Arsenio Rodriguez", "Sonora Matancera", "Orquesta Aragon",
        "Los Papines", "Irakere", "Gonzalo Rubalcaba", "Chucho Valdes", "Arturo Sandoval",
        "Yerba Buena", "Cubanismo", "Sierra Maestra", "Son 14", "Charanga Habanera",
        "Havana d Leo", "Los Originales de Manzanillo", "Adalberto Alvarez", "Juan Formell", "NG La Banda",
    ],
    "afrobeat": [
        "Burna Boy", "Wizkid", "Fela Kuti", "Davido", "Tems",
        "Mr Eazi", "Fireboy DML", "BNXN", "Asake", "Omah Lay",
        "Rema", "Ayra Starr", "Kizz Daniel", "Joeboy", "Simi",
        "Tiwa Savage", "Yemi Alade", "Waje", "Asa", "Angelique Kidjo",
        "Femi Kuti", "Made Kuti", "Seun Kuti", "Tony Allen", "Lagbaja",
        "Wasiu Ayinde", "King Sunny Ade", "Ebenezer Obey", "I.K. Dairo", "Victor Olaiya",
        "Youssou Ndour", "Baaba Maal", "Orchestra Baobab", "Super Diamono", "Ismael Lo",
        "Salif Keita", "Habib Koite", "Ali Farka Toure", "Boubacar Traore", "Oumou Sangare",
        "Miriam Makeba", "Hugh Masekela", "Dollar Brand", "Caiphus Semenya", "Letta Mbulu",
        "Brenda Fassie", "Yvonne Chaka Chaka", "Lucky Dube", "Sipho Mchunu", "Ladysmith Black Mambazo",
    ],
    "gospel": [
        "Kirk Franklin", "CeCe Winans", "Maverick City Music", "Lecrae",
        "Yolanda Adams", "Donnie McClurkin", "Fred Hammond", "Hezekiah Walker", "Karen Clark-Sheard",
        "Tye Tribbett", "Jason Nelson", "Jekalyn Carr", "William McDowell", "Travis Greene",
        "Jonathan McReynolds", "Koryn Hawthorne", "Kierra Sheard", "Erica Campbell", "Tasha Cobbs Leonard",
        "Marvin Sapp", "Deitrick Haddon", "Dorinda Clark-Cole", "Rance Allen", "Shirley Caesar",
        "James Cleveland", "Mahalia Jackson", "Thomas Dorsey", "Clara Ward", "Marion Williams",
        "Mississippi Mass Choir", "Brooklyn Tabernacle Choir", "Commissioned", "Witness", "Sounds of Blackness",
        "Chris Tomlin", "Matt Redman", "Hillsong Worship", "Elevation Worship", "Bethel Music",
        "Casting Crowns", "Third Day", "Newsboys", "Michael W. Smith", "Amy Grant",
        "Steffany Gretzinger", "Amanda Lindsey Cook", "Brian Johnson", "Cory Asbury", "Kari Jobe",
    ],
    "world-music": [
        "Shakira", "Cesaria Evora", "Buena Vista Social Club", "Youssou Ndour", "Rokia Traore",
        "Nusrat Fateh Ali Khan", "Ravi Shankar", "Ali Farka Toure", "Oumou Sangare", "Angelique Kidjo",
        "Salif Keita", "Tinariwen", "Toumani Diabate", "Ballake Sissoko", "Habib Koite",
        "Manu Chao", "Gogol Bordello", "DeVotchKa", "Beirut", "Balkan Beat Box",
        "Boban Markovic", "Fanfare Ciocarlia", "Taraf de Haidouks", "Emir Kusturica", "No Smoking Orchestra",
        "Mercedes Sosa", "Atahualpa Yupanqui", "Astor Piazzolla", "Gustavo Cerati", "Fito Paez",
        "Ibrahim Maalouf", "Marcel Khalife", "Fairuz", "Warda", "Om Kalthoum",
        "Orchestra Baobab", "Baaba Maal", "Ismaila Sane", "Orchestra Poly-Rythmo", "Bembeya Jazz",
        "Sanda Weigl", "Goran Bregovic", "Ivo Papasov", "Kocani Orkestar", "Ramadan Hussein",
        "Nujoud", "Waed Bouhassoun", "Naseer Shamma", "Anouar Brahem", "Rabih Abou-Khalil",
    ],
}


def _search_one_artist_sync(artist: str, limit: int = 10, offset: int = 0) -> list[dict]:
    """Search tracks for a single artist. Run via asyncio.to_thread.
    offset allows fetching different pages so repeated calls return different tracks.
    """
    import random as _random
    from spotipy.oauth2 import SpotifyClientCredentials
    settings = get_settings()
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
    ))
    query = f"artist:{artist}"
    safe_limit = min(limit, 50)
    tracks = []
    artist_lower = artist.lower()
    try:
        results = sp.search(q=query, type="track", limit=safe_limit, offset=offset)
        for item in results.get("tracks", {}).get("items", []):
            if not item or item.get("type") != "track":
                continue
            # Verify this track actually belongs to the target artist
            track_artists = [a["name"].lower() for a in item.get("artists", [])]
            if not any(artist_lower in ta or ta in artist_lower for ta in track_artists):
                continue
            tracks.append({
                "spotify_track_id": item["id"],
                "track_name": item.get("name", "Unknown"),
                "artist_name": ", ".join(a["name"] for a in item.get("artists", [])),
                "popularity": item.get("popularity", 0),
            })
    except Exception as e:
        print(f"[spotify_service] search error for {artist}: {e}")
    return tracks


async def search_tracks_by_artist(artist: str, limit: int = 10, offset: int = 0) -> list[dict]:
    """Search tracks for a single artist."""
    return await asyncio.to_thread(_search_one_artist_sync, artist, limit, offset)


async def search_tracks_by_genre(
    genres: list[str],
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Search genre-accurate tracks by rotating through curated artist list."""
    import random
    artist_pool: list[str] = []
    for g in genres:
        artist_pool.extend(_GENRE_ARTISTS.get(g, []))

    if not artist_pool:
        return []

    artist = random.choice(artist_pool)
    print(f"[spotify_service] searching artist: {artist!r} (genre={genres})")
    return await asyncio.to_thread(_search_one_artist_sync, artist, limit)


async def get_recommendations_by_seeds(
    access_token: str,
    seed_genres: list[str] = None,
    seed_tracks: list[str] = None,
    limit: int = 20,
    target_features: dict = None,
) -> list[dict]:
    """
    Cold start fallback：通过 genre/track seed 获取 Spotify 推荐
    target_features: {danceability, energy, valence, tempo, acousticness, instrumentalness}
    返回: [{spotify_track_id, track_name, artist_name, popularity}]
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    kwargs = {"limit": limit}
    if seed_genres:
        kwargs["seed_genres"] = seed_genres[:5]  # Spotify 最多 5 个 seed
    if seed_tracks:
        kwargs["seed_tracks"] = seed_tracks[:5]
    if target_features:
        for key, val in target_features.items():
            if val is not None:
                kwargs[f"target_{key}"] = round(float(val), 4)

    try:
        results = await loop.run_in_executor(
            None, lambda: sp.recommendations(**kwargs)
        )
    except Exception as e:
        print(f"[spotify_service] recommendations error: {e}")
        return []

    tracks = []
    for item in results.get("tracks", []):
        tracks.append({
            "spotify_track_id": item["id"],
            "track_name": item.get("name", "Unknown"),
            "artist_name": ", ".join(a["name"] for a in item.get("artists", [])),
            "popularity": item.get("popularity", 0),
        })
    return tracks


async def get_user_playlists(access_token: str, limit: int = 50) -> list[dict]:
    """
    Get user playlists.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_playlists(limit=limit)
    )

    playlists = []
    for item in results.get("items", []):
        image_url = item["images"][0]["url"] if item.get("images") else None
        playlists.append({
            "id": item["id"],
            "name": item.get("name", "Unknown"),
            "description": item.get("description", ""),
            "track_count": item.get("tracks", {}).get("total", 0),
            "image_url": image_url,
            "owner_name": item.get("owner", {}).get("display_name", "Unknown"),
        })
    return playlists


async def get_user_liked_songs(access_token: str, limit: int = 50) -> dict:
    """
    Get user Liked Songs metadata.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_saved_tracks(limit=limit)
    )

    track_count = results.get("total", 0)

    return {
        "id": "liked_songs",
        "name": "Liked Songs",
        "description": "Your liked songs",
        "track_count": track_count,
        "image_url": None,
        "owner_name": "Spotify"
    }


async def get_user_liked_songs_tracks(access_token: str, limit: int = 50) -> list[dict]:
    """
    Get user Liked Songs track list.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.current_user_saved_tracks(limit=limit)
    )

    tracks = []
    for item in results.get("items", []):
        track_obj = item.get("track")
        if not track_obj or track_obj.get("type") != "track":
            continue

        album_name = track_obj.get("album", {}).get("name", "Unknown")
        artists = ", ".join(a.get("name", "") for a in track_obj.get("artists", []))

        tracks.append({
            "spotify_track_id": track_obj["id"],
            "track_name": track_obj.get("name", "Unknown"),
            "artist_name": artists,
            "album_name": album_name,
            "popularity": track_obj.get("popularity", 0),
        })
    return tracks


async def get_playlist_tracks(access_token: str, playlist_id: str, limit: int = 100) -> list[dict]:
    """
    Get tracks in a playlist.
    """
    sp = spotipy.Spotify(auth=access_token)
    loop = asyncio.get_event_loop()

    results = await loop.run_in_executor(
        None, lambda: sp.playlist_tracks(playlist_id, limit=limit)
    )

    tracks = []
    for item in results.get("items", []):
        # Spotify API may use 'track' or 'item' as key
        track_obj = item.get("track") or item.get("item")
        # Filter out null entries and episodes
        if not track_obj or track_obj.get("type") != "track":
            continue
            
        album_name = track_obj.get("album", {}).get("name", "Unknown")
        artists = ", ".join(a.get("name", "") for a in track_obj.get("artists", []))
        
        tracks.append({
            "spotify_track_id": track_obj["id"],
            "track_name": track_obj.get("name", "Unknown"),
            "artist_name": artists,
            "album_name": album_name,
            "popularity": track_obj.get("popularity", 0),
        })
    return tracks
