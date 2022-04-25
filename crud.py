"""logic/functions/methods for database"""

from model import Track, Feat, Playlist, Likes, User, connect_to_db, db
from random import choice
import search_helpers

## imported to crud from server on 4/19
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

##spotipy finds the credentials in the environment and sets it to auth_manager
##for searching and ClientCredentials flow
authorization = SpotifyClientCredentials()
spot = spotipy.Spotify(auth_manager=authorization)
url = 'https://api.spotify.com/v1/search?'
app_id = os.environ['APP_ID']

scope = 'playlist-modify-public'
spot2 = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


'''
# results = spot.search(q='',type='track',limit=50)
songs = results['tracks']['items']
for song in songs:
    song['uri']
    song['name']
    song['artists'][0]['name']

# tracks = spot.playlist_tracks(playlist_id)

# new = spot2.user_playlist_create(app_id, 'play_name')
new playlist redirects to a new page, set it specifically
play more with the redirect and authorization, it's confusing
'''


## below functions create new instances for each table

def create_track(track_id, title, artist):
    """take Spotify info and return a new track in local db."""
    
    track = Track(
        track_id=track_id,
        title=title,
        artist=artist)
    
    return track

def create_feat(track_id, playlist_id):
    """Create a connection between track and playlist"""
    
    feat = Feat(
        track_id=track_id,
        play_id=playlist_id)
    
    return feat

def create_playlist(play_id, name, creator_id, hype=0):
    """Create and return a new playlist"""

    playlist = Playlist(
        play_id=play_id, 
        name=name, 
        creator_id=creator_id,
        hype=hype)

    return playlist

def create_like(user_id, playlist_id):
    """Create a connection between a playlist and a user who didn't author it"""

    like = Likes(
        like_id= str(user_id)+playlist_id,
        user_id = user_id,
        play_id = playlist_id)

    return like

def create_user(name, email, pw, spot_id=None):
    """Add a new user to the app"""
    
    user = User(
        spot_id=spot_id,
        name=name,
        email=email,
        pw = pw)
    
    return user


## functions for creating an account, logging in, and confirming email isn't taken

def check_email(email):
    '''checks if email is already in db, returns list of user exists '''

    check = User.query.filter(User.email==email).all()

    return check
    
def log_in(email, password):
    '''checks a user's password, returns their id if successful
    flase if password wrong or email not in db'''

    user = check_email(email)

    if len(user) == 1:
        user = user[0]

        if user.pw == password:
            return user.user_id
    
    return False

def make_account(email, password, name):
    '''checks if user email is taken
    if not, creates an account
    returns new users' id
    
    returns false if email is taken'''

    if len(check_email(email)) == 0:
        new = create_user(name=name, email=email, pw=password)
        db.session.add(new)
        db.session.commit()
        return new.user_id
    else: 
        return False


## functions for creating playlists from user input phrases
## TODO: tighten up the search with searcher-helper functions

def search_tracks_by_title(queries):
    '''search for songs from db for the given set of search parameters phrase in a text'''

    search = Track.query.filter(Track.title.in_(queries)).all()

    return search

def search_api(word, offset=0):
    '''performs an api search for the given phrase'''

    result = spot.search(q=word, type='track', limit=50, offset=offset)

    return result

def make_track(results):
    '''goes through set of API search results and turns into tracks'''

    new = []
    for item in results['tracks']['items']:
        if Track.query.get(item['id']) == None:
            new.append(create_track(
                item['id'], 
                item['name'], 
                item['artists'][0]['name']))

    db.session.add_all(new)
    db.session.commit()

def find_songs_for_play(query):
    '''searches through db, api, on repeat until tracks all found'''

    search = search_tracks_by_title(query)

    q_num = 0
    while len(search) == 0:
        new_search = search_api(query[0], q_num)
        make_track(new_search)
        search = search_tracks_by_title(query)
        q_num += 1

        if q_num > 10:
            break

    return search

def pick_songs(search_results):
    '''pick a random option from the results to pick for playlist'''

    if len(search_results) > 0:
        return choice(search_results)


def make_playlist(phrase, author):
    '''takes in a given phrase and makes a spotify playlist full of songs
    currently the first word from title spells out the word

    returns the playlist id
    '''
  
    ## cannot give spotify ownership to users - TODO:
    ## figure out how to give it to them
    # if author.spot_id == None:
    #     id_ = app_id
    # else:
    #     id_ = author.spot_id

    new = spot2.user_playlist_create(app_id, phrase)
    playlist = create_playlist(new['id'], phrase, author.user_id)

    query_dict = search_helpers.make_search_options(phrase)
    
    tracks = []
    for query in query_dict:
        songs_opts = find_songs_for_play(query_dict[query])
        song_pick = pick_songs(songs_opts)

        #TODO: 
        '''
        do something here to check the length of the track title.
        
        if a word can only be incorporated by ngram than the neighbors within that ngram
        don't need their own tracks'''
        
        if song_pick != None:
            tracks.append(song_pick)


    play_fs = [playlist]
    for track in tracks:
        spot.playlist_add_items(new['id'], [track.track_id])
        feat = create_feat(track.track_id, playlist.play_id)
        play_fs.append(feat)

    db.session.add_all(play_fs)
    db.session.commit()

    return playlist.play_id


# function for searching through the db for playlists featuring keywords
# looks through track title and artists

def search_db(query):
    '''searches through playlist db for query keywords

    SELECT name FROM playlists AS P
    JOIN feats AS f ON p.play_id=f.play_id
    JOIN tracks AS t ON f.track_id=t.track_id
    WHERE t.title LIKE '%keyword%' OR t.artist LIKE '%keyword%'
    '''

    play_q = db.session.query(Playlist)
    join_feat = play_q.join(Feat, Playlist.play_id==Feat.play_id)
    play_feat_track = join_feat.join(Track, Track.track_id==Feat.track_id)
    where = play_feat_track.filter((Track.title.like(f'{query}%')) | (Track.artist.like(f'{query}%')))
    
    results = where.all()
    final = []

    if len(results) > 0:
        for item in results:
            author = User.query.get(item.creator_id)
            final.append([item.play_id, item.name, author.name])
    else:
        final.append(["None", "No results", "Community"])

    return final


def make_like(user_id, playlist_id):
    '''checks that the user didn't author the playlist
    checks that the user hasn't already liked the playlist
    checks that the user is logged in
    
    if all pass creates a like instance
    return success message
    or specific failure message
    '''
    playlist = Playlist.query.get(playlist_id)

    if user_id == False:
        return("You need to be logged in to like")
    else:
        if playlist.creator_id == user_id:
            return "You made this playlist"
        else:
            if Likes.query.get(str(user_id)+playlist_id):
                return "You already liked this"
            else:
                like = create_like(user_id, playlist_id)
                db.session.add(like)
                playlist.hype += 1
                db.session.commit()
                return "Liked!"


if __name__ == '__main__':
    from server import app
    connect_to_db(app)




# def make_feats(playlist):

#     tracks = spot.playlist_items(playlist.play_id)
#     items = tracks['items']
#     feats = []
#     for item in items:
#         id = item['track']['id']
#         title = item['track']['name']
#         artist = item['track']['artists'][0]['name']


#         if Track.query.get(id) == None:
#             song = create_track(id, title, artist)
#             db.session.add(song)
#             db.session.commit()

#         feat = create_feat(id, playlist.play_id)
#         feats.append(feat)

#     db.session.add_all(feats)
#     db.session.commit()

#     return feats