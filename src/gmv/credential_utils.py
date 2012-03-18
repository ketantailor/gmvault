'''
Created on Jan 19, 2012

@author: guillaume.aubert@gmail.com

 Module handling the xauth authentication.
 Strongly influenced by http://code.google.com/p/googlecl/source/browse/trunk/src/googlecl/service.py
 and xauth part of gyb http://code.google.com/p/got-your-back/source/browse/trunk/gyb.py

'''
import gdata.service
import webbrowser
import random
import time
import atom
import urllib

import os
import getpass

import log_utils
import blowfish
import gmvault_utils

LOG = log_utils.LoggerFactory.get_logger('oauth')



def get_oauth_tok_sec(email, use_webbrowser = False, debug=False):
    '''
       Generate token and secret
    '''
    
    scopes = ['https://mail.google.com/', # IMAP/SMTP client access
              'https://www.googleapis.com/auth/userinfo#email'] # Email address access (verify token authorized by correct account
    
    gdata_serv = gdata.service.GDataService()
    gdata_serv.debug = debug
    gdata_serv.source = 'gmvault '
    
    gdata_serv.SetOAuthInputParameters(gdata.auth.OAuthSignatureMethod.HMAC_SHA1, \
                                       consumer_key = 'anonymous', consumer_secret = 'anonymous')
    
    params = {'xoauth_displayname':'gmvault - Backup your Gmail account'}
    try:
        request_token = gdata_serv.FetchOAuthRequestToken(scopes=scopes, extra_parameters = params)
    except gdata.service.FetchingOAuthRequestTokenFailed, err:
        if str(err).find('Timestamp') != -1:
            LOG.critical('Is your system clock up to date? See the FAQ http://code.google.com/p/googlecl/wiki/FAQ'\
                         '#Timestamp_too_far_from_current_time')
        else:
            LOG.error('error %s' % (err))
            #LOG.error(err[0]['body'].strip() + '; Request token retrieval failed!')
        return (None, None)
    
    url_params = {}
    domain = email[email.find('@')+1:]
    if domain.lower() != 'gmail.com' and domain.lower() != 'googlemail.com':
        url_params = {'hd': domain}
    
    auth_url = gdata_serv.GenerateOAuthAuthorizationURL(request_token=request_token, extra_params=url_params)
    
    #message to indicate that a browser will be opened
    raw_input('gmvault will now open a web browser page in order for you to grant gmvault access to your Gmail.\n'\
              'Please make sure you\'re logged into the correct Gmail account (%s) before granting access.\n'\
              'Press ENTER to open the browser. Once you\'ve granted access you can switch back to gmvault.' % (email))
    
    # run web browser otherwise print message with url
    if use_webbrowser:
        try:
            webbrowser.open(str(auth_url))  
        except Exception, err: 
            LOG.exception(err)
        
        raw_input("You should now see the web page on your browser now.\n"\
                  "If you don\'t, you can manually open:\n\n%s\n\nOnce you've granted gmvault access, press the Enter key.\n" % (auth_url))
        
    else:
        raw_input('Please log in and/or grant access via your browser at %s '
                  'then hit enter.' % (auth_url))
    
    try:
        final_token = gdata_serv.UpgradeToOAuthAccessToken(request_token)
    except gdata.service.TokenUpgradeFailed:
        LOG.critical('Token upgrade failed! Could not get OAuth access token.\n Did you grant gmvault access in your browser ?')

        return (None, None)

    return (final_token.key, final_token.secret)

def generate_xoauth_req(a_token, a_secret, email, two_legged=False):
    """
       generate the xoauth req from a user token and secret.
       Handle two_legged xoauth for admins.
    """
    nonce = str(random.randrange(2**64 - 1))
    timestamp = str(int(time.time()))
    if two_legged:
        request = atom.http_core.HttpRequest('https://mail.google.com/mail/b/%s/imap/?xoauth_requestor_id=%s' % (email, urllib.quote(email)), 'GET')
         
        signature = gdata.gauth.generate_hmac_signature(http_request=request, consumer_key=a_token, consumer_secret=a_secret, \
                                                        timestamp=timestamp, nonce=nonce, version='1.0', next=None)
        return '''GET https://mail.google.com/mail/b/%s/imap/?xoauth_requestor_id=%s oauth_consumer_key="%s",oauth_nonce="%s",oauth_signature="%s",oauth_signature_method="HMAC-SHA1",oauth_timestamp="%s",oauth_version="1.0"''' % (email, urllib.quote(email), a_token, nonce, urllib.quote(signature), timestamp)
    else:
        request = atom.http_core.HttpRequest('https://mail.google.com/mail/b/%s/imap/' % email, 'GET')
        signature = gdata.gauth.generate_hmac_signature(
            http_request=request, consumer_key='anonymous', consumer_secret='anonymous', timestamp=timestamp,
            nonce=nonce, version='1.0', next=None, token = a_token, token_secret= a_secret)
        return '''GET https://mail.google.com/mail/b/%s/imap/ oauth_consumer_key="anonymous",oauth_nonce="%s",oauth_signature="%s",oauth_signature_method="HMAC-SHA1",oauth_timestamp="%s",oauth_token="%s",oauth_version="1.0"''' % (email, nonce, urllib.quote(signature), timestamp, urllib.quote(a_token))




class CredentialHelper(object):
    
    @classmethod
    def get_secret(cls):
        """
           Get a secret from secret file or generate it
        """
        secret_file_path = '%s/token.sec' % (gmvault_utils.get_home_dir_path())
        if os.path.exists(secret_file_path):
            secret = open(secret_file_path).read()
        else:
            secret = gmvault_utils.make_password()
            fdesc = open(secret_file_path, 'w+')
            fdesc.write(secret)
            fdesc.close()
        
        return secret
    
    @classmethod
    def store_passwd(cls, email, passwd):
        """
        """
        passwd_file = '%s/%s.passwd' % (gmvault_utils.get_home_dir_path(), email)
    
        fdesc = open(passwd_file, "w+")
        
        cipher       = blowfish.Blowfish(cls.get_secret())
        cipher.initCTR()
    
        fdesc.write(cipher.encryptCTR(passwd))
    
        fdesc.close()
        
    @classmethod
    def store_oauth_credentials(cls, email, token, secret):
        """
        """
        oauth_file = '%s/%s.oauth' % (gmvault_utils.get_home_dir_path(), email)
    
        fdesc = open(oauth_file, "w+")
        
        fdesc.write(token)
        fdesc.write('::')
        fdesc.write(secret)
    
        fdesc.close()
    
    @classmethod
    def read_password(cls, email):
        """
           Read password credentials
           Look for the defined in env GMVAULT_DIR so by default to ~/.gmvault
           Look for file GMVAULT_DIR/email.passwd
        """
        gmv_dir = gmvault_utils.get_home_dir_path()
        
        #look for email.passwed in GMV_DIR
        user_passwd_file_path = "%s/%s.passwd" % (gmv_dir, email)

        password = None
        if os.path.exists(user_passwd_file_path):
            passwd_file  = open(user_passwd_file_path)
            
            password     = passwd_file.read()
            cipher       = blowfish.Blowfish(cls.get_secret())
            cipher.initCTR()
            password     = cipher.decryptCTR(password)

            LOG.debug("password=[%s]" % (password))
        
        return password
    
    @classmethod
    def read_oauth_tok_sec(cls, email):
        """
           Read oauth token secret credential
           Look for the defined in env GMVAULT_DIR so by default to ~/.gmvault
           Look for file GMVAULT_DIR/email.oauth
        """
        gmv_dir = gmvault_utils.get_home_dir_path()
        
        #look for email.passwed in GMV_DIR
        user_oauth_file_path = "%s/%s.oauth" % (gmv_dir, email)

        token  = None
        secret = None
        if os.path.exists(user_oauth_file_path):
            LOG.critical("Use oauth credentials from %s." % (user_oauth_file_path))
            
            oauth_file  = open(user_oauth_file_path)
            
            try:
                token, secret = oauth_file.read().split('::')
            except Exception, err:
                LOG.error("Error when reading oauth info from %s" % (user_oauth_file_path))
                
                LOG.exception(err)
                
                LOG.critical("Cannot read oauth credentials from %s. Force oauth credentials renewal." % (user_oauth_file_path))
        
        if token: token   = token.strip()
        if secret: secret = secret.strip() 
        
        return token, secret
            
    @classmethod
    def get_credential(cls, args, test_mode = {'activate': False, 'value' : 'test_password'}):
        """
           Deal with the credentials.
           1) Password
           --passwd passed. If --passwd passed and not password given if no password saved go in interactive mode
           2) XOAuth Token
        """
        
        
        credential = { }
        
        #first check that there is an email
        if not args.get('email', None):
            raise Exception("No email passed, Need to pass an email")
        
        if args['passwd'] in ['empty', 'store', 'renew']: 
            # --passwd is here so look if there is a passwd in conf file 
            # or go in interactive mode
            passwd = cls.read_password(args['email'])
            
            #password to be renewed so need an interactive phase to get the new pass
            if not passwd or args['passwd'] in ['renew', 'store']: # go to interactive mode
                if not test_mode.get('activate', False):
                    passwd = getpass.getpass('Please enter gmail password for %s and press enter:' % (args['email']))
                else:
                    passwd = test_mode.get('value', 'no_password_given')
                    
                credential = { 'type' : 'passwd', 'value' : passwd}
                
                #store it in dir if asked for --store-passwd or --renew-passwd
                if args['passwd'] in ['renew', 'store']:
                    cls.store_passwd(args['email'], passwd)
                    credential['option'] = 'saved'
            else:
                credential = { 'type' : 'passwd', 'value' : passwd, 'option':'read' }
                               
        #elif args['passwd'] == 'not_seen' and args['oauth']:
        elif args['passwd'] == None and args['oauth']:
            # get token secret
            # if they are in a file then no need to call get_oauth_tok_sec
            # will have to add 2 legged or 3 legged
            LOG.critical("Oauth will be used for authentication.\n")
            
            token, secret = cls.read_oauth_tok_sec(args['email'])
           
            if not token: 
                token, secret = get_oauth_tok_sec(args['email'], use_webbrowser = True)
                #store newly created token
                cls.store_oauth_credentials(args['email'], token, secret)
               
            #LOG.debug("token=[%s], secret=[%s]" % (token, secret))
            
            xoauth_req = generate_xoauth_req(token, secret, args['email'])
            
            LOG.critical("Successfully read oauth credentials.\n")

            credential = { 'type' : 'xoauth', 'value' : xoauth_req, 'option':None }
                        
        return credential

    @classmethod
    def get_xoauth_req_from_email(cls, email):
        """
           This will be used to reconnect after a timeout
        """
        token, secret = cls.read_oauth_tok_sec(email)
        if not token: 
            raise Exception("Error cannot read token, secret from")
        
        xoauth_req = generate_xoauth_req(token, secret, email)
        
        return xoauth_req




if __name__ == '__main__':
    
    """
algo:
get key and secret
if key and secret in conf take it
otherwise generate them with get_oauth_tok_sec
save secret once you have it (encrypt or not ?)
generate xoauth everytime your connect to imap
do not use atom to create the request (no need to get a fake dependency
"""
    log_utils.LoggerFactory.setup_cli_app_handler(activate_log_file=True, file_path="./gmvault.log") 
    
    token, secret = get_oauth_tok_sec('guillaume.aubert@gmail.com')
    print('token = %s, secret = %s' % (token,secret) )
    req = generate_xoauth_req(token, secret, 'guillaume.aubert@gmail.com')
    
    print(req)