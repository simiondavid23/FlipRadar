from cryptography.hazmat.primitives.asymmetric import ec 
from cryptography.hazmat.backends import default_backend 
import base64 
pk = ec.generate_private_key(ec.SECP256R1(), default_backend()) 
pub = pk.public_key() 
priv_b = pk.private_numbers().private_value.to_bytes(32, 'big') 
pn = pub.public_numbers() 
pub_b = b'\x04' + pn.x.to_bytes(32, 'big') + pn.y.to_bytes(32, 'big') 
print('VAPID_PUBLIC_KEY=' + base64.urlsafe_b64encode(pub_b).rstrip(b'=').decode()) 
print('VAPID_PRIVATE_KEY=' + base64.urlsafe_b64encode(priv_b).rstrip(b'=').decode()) 
