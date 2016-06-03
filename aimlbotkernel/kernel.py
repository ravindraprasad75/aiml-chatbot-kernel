"""
The main file for the AIML Chatbot Jupyter kernel
"""

from __future__ import absolute_import, division, print_function

import sys
import os
import aiml
import logging

from ipykernel.kernelbase import Kernel
from traitlets import List

from . import __version__
from .aimlbot import AimlBot, build_aiml
from .utils import KrnlException, data_msg

# The logger we will use
LOG = logging.getLogger( __name__ )

# Load commands for the standard DBs
LOAD = { 'alice' : 'alice',
         'standard' : 'aiml b' }


# -----------------------------------------------------------------------

# The list of implemented magics with their help, as a pair [param,help-text]
magics = { 
    '%lsmagics' : [ '', 'list all magics'], 
    '%help' : [ '', 'show general help' ],
    '%learn' : [ 'alice | standard | <dbdirectory> | <xml-file>',
                 'learn an AIML db' ],
    '%forget' : [ '', 'reset the bot' ],
    '%aiml' : [ '', 'add additional AIML rules' ],
    '%show size' : [ '', 'show the number of categories loaded in the bot' ], 
    '%show session' : [ '', 'show the predicates defined in the session' ],
    '%setp' : [ '[bot] <name> <value>','set a predicate, or a bot predicate'],
    '%save' : [ '<name>','save bot state to a file'],
    '%load' : [ '<name>','load bot state from a file'],
}


# The full list of all magics
magic_help = ('Available magics:\n' + 
              '  '.join( sorted(magics.keys()) ) + 
              '\n\n' +
              '\n'.join( ('{0} {1} : {2}'.format(k,*magics[k]) 
                          for k in sorted(magics) ) ) )

# The generic help message
general_help = """AIML Chatbot

You can start by loading a database of rules:

%learn alice | standard | <dbdirectory> | <xml-file>

For "alice" & "standard" databases, the rules will
automatically be activated. For a custom database,
you will need to launch the "load <name>" command
defined in it.

Once loaded, you can start chatting with the bot. 

New databases can be added by additional "%learn" commands.

Use "%lsmagic" to see all the available magics.
"""


# -----------------------------------------------------------------------


def split_magics( buffer ):
    """
    Split the cell by lines and decide if it contains magic or bot input
    """
    # Split by lines & remove comments
    buffer_lines = [ l for l in buffer.split('\n') if not l or l[0] !='#' ]

    # Remove leading empty lines
    for i, line in enumerate(buffer_lines):
        if line:
            break
    if i:
        buffer_lines = buffer_lines[i:]

    # Return
    if not buffer_lines:
        return None, None
    elif buffer_lines[0][0] == '%':
        return buffer_lines, True
    else:
        return u'\n'.join(buffer_lines), False
         

def is_magic( token, token_start, buf ):
    """
    Detect if the passed token corresponds to a magic command: starts
    with a percent, and it's at the beginning of the buffer
    """
    return token[0] == '%' and token_start==0


def token_at_cursor( code, pos=0 ):
    """
    Find the token present at the passed position in the code buffer
    """
    l = len(code)
    end = start = pos
    # Go forwards while we get alphanumeric chars
    while end<l and code[end].isalpha():
        end+=1
    # Go backwards while we get alphanumeric chars
    while start>0 and code[start-1].isalpha():
        start-=1
    # If previous character is a %, add it (potential magic)
    if start>0 and code[start-1] == '%':
        start -= 1
    return code[start:end], start



# -----------------------------------------------------------------------

class AimlBotKernel(Kernel):

    implementation = 'Chatbot'
    implementation_version = __version__

    language = 'xml'
    language_version = '0.1'
    banner = "AIML Chatbot - a chatbot for Jupyter"
    language_info = { 'name': 'Chatbot', 'mimetype': 'text/xml'}

    help_links = List([
        {
            'text': "ALICE AI Foundation",
            'url': "http://www.alicebot.org"
        },
        {
            'text' : 'AIML 1.0.1',
            'url' : 'http://www.alicebot.org/TR/2001/WD-aiml/'
        },
        {
            'text' : 'AIML Tutorial',
            'url' : 'https://www.pandorabots.com/botmaster/en/tutorial?ch=0'
        },
    ])


    def __init__(self, *args, **kwargs):
        # Start base kernel
        super(AimlBotKernel, self).__init__(*args, **kwargs)
        # Redirect stdout
        try:
            sys.stdout.write = self._send_stdout
        except:
            LOG.warn( "can't redirect stdout" )
        # Start the AIML kernel
        self.bot = AimlBot()


    # -----------------------------------------------------------------


    def _send( self, data, status='ok', silent=False ):
        """
        Send a response to the frontend and return an execute message
        """
        # Data to send back
        if data is not None and not silent:
            LOG.info( 'output: %s', data )
            # Format the data
            data = data_msg( data, mtype=status )
            # Send the data to the frontend
            self.send_response( self.iopub_socket, 'display_data', data )

        # Result message
        return {'status': 'error' if status == 'error' else 'ok',
                # The base class will increment the execution count
                'execution_count': self.execution_count,
                'payload' : [],
                'user_expressions': {},
               }


    def _send_stdout(self, txt):
        """
        Send to frontend the data received as stdout
        """
        stream_content = { 'name': 'stdout', 'text': txt, 'metadata': {} }
        LOG.debug('stdout: %s' % txt)
        self.send_response(self.iopub_socket, 'stream', stream_content)


    def learn_file( self, name ):
        """
        Load rules from AIML files
        """
        # A direct file to load
        if name.endswith('.xml') or name.endswith('aiml'):
            self._send( ("Learning patterns in {}", name), 'ctrl' )
            self.bot.learn( name )
            return

        # A directory containing: AIML files + a startup file
        if name in ('alice','standard'):
            dbdir = os.path.join( os.path.dirname(aiml.__file__), name )
        elif os.path.isdir( name ):
            if not os.path.isfile( os.path.join(name,'startup.xml') ):
                raise KrnlException( "Error: missing startup file in '{}", name)
        else:
            raise KrnlException( 'unimplemented learn for {}', name )
        
        self._send( ("Learning database: '{}'", name), status='ctrl' )
        prev = os.getcwd()
        try:
            LOG.info( ' find db in: %s',dbdir)
            os.chdir( dbdir )
            LOG.info( ' learn startup.xml' )
            self.bot.learn( 'startup.xml' )
            if LOAD.get(name ):
                LOG.info( ' load '+ LOAD[name] )
                self._send( "Loading patterns", 'ctrl' )
                self.bot.respond( 'load ' + LOAD[name] )
        finally:
            os.chdir( prev )


    def learn_cell( self, lines ):
        """
        Learn rules from a notebook cell
        """
        # Remove leading empty lines
        for i, l in enumerate(lines):
            if l:
                break
        if i:
            lines = lines[i:]
        fmt = 'aiml' if lines[0].startswith('<') else 'text'
        self.bot.learn_buffer( lines, fmt )


    def magic( self, lines ):
        """
        Process magic cells
          @param lines (list): list of lines containing magics

        For most of the magics only one magic line is recognized. The
        exceptions are %aiml (which uses the whole cell) and %setp (which
        can appear multiple times in a cell).
        """
        kw = lines[0].split()
        magic = kw[0][1:].lower()

        if magic in ('?','help'):

            return general_help, 'help'

        elif magic.startswith( 'lsmagic' ):

            return magic_help, 'help'

        elif magic == "save":
            
            if len(kw) < 2:
                raise KrnlException( 'missing filename for save operation' )
            return self.bot.saveBrain(kw[1]), 'ctrl'

        elif magic == "load":
            
            if len(kw) < 2:
                raise KrnlException( 'missing filename for load operation' )
            try:
                return self.bot.loadBrain(kw[1]), 'ctrl'
            except IOError as e:
                raise KrnlException( "can't load {}: {!s}", kw[1], e )

        elif magic == "learn":

            before = self.bot.numCategories()
            if len(kw) < 2:
                raise KrnlException( 'missing learn param' )
            self.learn_file( kw[1] ), 'ctrl'
            msg = 'Loaded {} new patterns', self.bot.numCategories() - before
            return msg, 'ctrl'

        elif magic == "aiml":

            before = self.bot.numCategories()
            self.learn_cell( lines[1:] )
            msg = 'Loaded {} new patterns', self.bot.numCategories() - before
            return msg, 'ctrl'

        elif magic == "setp":

            out = []
            for line in lines:
                # Fetch parameters
                try:
                    cmd, name, value = line.split(None,2)
                    if cmd != '%setp':
                        raise KrnlException(u'invalid magic in setp cell: {}',cmd)
                except ValueError:
                    raise KrnlException(u'missing setp predicate: {}',line)

                # Set the predicate
                if name != 'bot':
                    self.bot.setPredicate( name, value )
                    out.append(u'Setting predicate: {} = {}'.format(name,value))
                else:
                    try:
                        nam, val = value.split(None,1)
                    except ValueError:
                        raise KrnlException('missing setp bot predicate param')
                    self.bot.setBotPredicate( nam, val )
                    out.append(u'Setting bot predicate: {} = {}'.format(nam,val))

            return u'\n'.join(out), 'ctrl'

        elif magic in ("forget","reset"):

            self.bot.resetBrain()
            return 'Resetting bot brain', 'ctrl'

        elif magic == "show":

            if len(kw) < 2:
                raise KrnlException( 'missing show param' )                
            if kw[1].startswith('size'):
                msg = "Number of loaded categories: {}",self.bot.numCategories()
                return msg, 'info'
            elif kw[1].startswith('ses'):
                sdata = self.bot.getSessionData()
                fields = [ u'  {}: {}'.format(k,sdata['_global'][k]) 
                           for k in sorted(sdata['_global'].iterkeys())
                           if not k[0].startswith('_') ]
                return "Session fields:\n" + "\n".join(fields), 'info'
            else:
                raise KrnlException( 'unknown show magic: {}', kw[1] )

        elif magic == "log":

            if len(kw) < 2:
                raise KrnlException( 'missing log param' )
            try:
                l = kw[1].upper()
                parent_logger = logging.getLogger( __name__.rsplit('.',1)[0] )
                parent_logger.setLevel( l )
                return ("Logging set to {}", l), 'ctrl'
            except ValueError:
                raise KrnlException( 'unknown log level: {}', kw[1] )

        else:
            raise KrnlException( 'unknown magic: {}', magic )


        
    def _inner_execute( self, code, silent ):
        """
        Execute the cell code, send the appropriate message to the frontend
        and return the result to be provided to the backend
        """
        LOG.info( ' input: %s', code )
        content, is_magic = split_magics( code )

        if is_magic is True:
            return self._send( *self.magic(content) )
        elif is_magic is False:
            if self.bot.numCategories() == 0:
                return self._send( general_help, 'help' )
            response = self.bot.respond(content.encode('utf-8')).decode('utf-8')
            return self._send( response, 'bot' )


    # -----------------------------------------------------------------


    def do_execute( self, code, silent, store_history=True,
                    user_expressions=None, allow_stdin=False ):
        """
        Jupyter kernel execute message
        """

        try:
            return self._inner_execute( code, silent )
        except KrnlException as e:
            return self._send( e, silent=silent, status='error' )
        except Exception as e:
            #raise
            return self._send( KrnlException(e), silent=silent, status='error' )
            


    # -----------------------------------------------------------------

    def do_complete(self, code, cursor_pos ):
        """
        Method called on autocompletion requests
        """
        tkn_low = code.lower().split(None,1)[0]
        start = 0
        if code and code[0] == '%':
            matches = [ k for k in magics.keys() if k.startswith(tkn_low) ]
        LOG.debug( "token={%s} matches={%r}", tkn_low, matches )

        if matches:
            return  {'status': 'ok',
                     'cursor_start' : start,
                     'cursor_end': start+len(tkn_low),
                     'matches' : matches }


    # -----------------------------------------------------------------

    def do_inspect(self, code, cursor_pos, detail_level=0):
        """
        Method called on help requests
        """
        LOG.info( "{%s}", code[cursor_pos:cursor_pos+10] )

        # Find the token for which help is requested
        token, start = token_at_cursor( code, cursor_pos )

        # Find the help for this token
        if not is_magic( token, start, code ):
            info = None
        elif token == '%':
            info = magic_help
        else:
            info = magics.get( token, None )
            if info:
                info = '{} {}\n\n{}'.format(token,*info)

        return { 'status' : 'ok',
                 'data' : { 'text/plain' : info },
                 'metadata' : {},
                 'found' : info is not None
               }

    # -----------------------------------------------------------------