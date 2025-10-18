from datetime import timedelta
from time import sleep
import pytest
from utilities import security

def test_HashAndVerifyPassword():
    pwd1 = 'aoisdjfifj'
    hpwd1 = security.hashPassword(pwd1)
    pwd2 = 'aisjdfoiasp'

    # Test if hashing function works
    assert pwd1 != hpwd1 and type(hpwd1) == str

    # Test if hashing function outputs different result at different time
    assert hpwd1 != security.hashPassword(pwd1)

    # Test verification pass
    assert security.verifyPassword(pwd1, hpwd1)

    # Test verification fail
    assert not security.verifyPassword(pwd2, hpwd1)

def test_CreateAndValidateToken():
    payload1 = {
        "sub": '123',
        "name": "John Deo"
    }
    exp1 = timedelta(minutes=5)
    exp2 = timedelta(minutes=0)
    sec1 = "askdjfka12h3j12312kj3123123sdfjlkaSdjflk"
    sec2 = "askdjfka12h3j12312kj3123123sdfjlka5djflk"

    tok1 = security.createToken(payload1, exp1, sec1)
    tok2 = security.createToken(payload1, exp2, sec1)

    # Test if token is created
    assert type(tok1) == str
    
    # Test if token with same payload but created at different time(delta >= 1sec) is different
    sleep(1)
    assert tok1 != security.createToken(payload1, exp1, sec1)

    # Test if token can be decoded with corresponding key and payload is correct
    assert security.validateToken(
        tok1, sec1
    )['sub'] == '123'

    assert security.validateToken(
        tok1, sec1
    )['name'] == 'John Deo'

    assert security.validateToken(
        security.createToken(payload1, exp1, sec2), sec1
    ) == None

    # Test if token expires correctly
    assert security.validateToken(
        tok2, sec1
    ) == None