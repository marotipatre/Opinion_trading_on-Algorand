import algokit_utils
import logging
import algosdk
import pytest
from algokit_utils.beta.account_manager import AddressAndSigner
from algokit_utils.beta.algorand_client import (
    AlgorandClient,
    AssetCreateParams,
    AssetOptInParams,
    AssetTransferParams,
    PayParams,
)
from algosdk.atomic_transaction_composer import TransactionWithSigner

from smart_contracts.artifacts.opinion_market.opinion_trading_client import (
    OpinionTradingClient,
)
# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@pytest.fixture(scope="session")
def algorand() -> AlgorandClient:
    """Get an AlgorandClient to use throughout the tests"""
    return AlgorandClient.default_local_net()


@pytest.fixture(scope="session")
def dispenser(algorand: AlgorandClient) -> AddressAndSigner:
    """Get the dispenser to fund test addresses"""
    return algorand.account.dispenser()


@pytest.fixture(scope="session")
def creator(algorand: AlgorandClient, dispenser: AddressAndSigner) -> AddressAndSigner:
    acct = algorand.account.random()
    

    # Make sure the account has some ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )
    
    return acct

@pytest.fixture(scope="session")
def opinion_market_client(algorand: AlgorandClient, creator: AddressAndSigner) -> OpinionTradingClient:
    """Instantiate an aplpication client we can use for our tests"""
    client = OpinionTradingClient(
        algod_client=algorand.client.algod,
        sender=creator.address,
        signer=creator.signer,
    )

    # Create an instance of our application on the network
    client.create_create_market(market_question="Is Algorand the best blockchain?",
        outcome_a="Yes",
        outcome_b="No",
        expiration_time=1234567890,
        )
    
    return client

def test_pass(opinion_market_client: OpinionTradingClient):
    pass

def test_buy_shares_a(
    opinion_market_client: OpinionTradingClient,
    creator: AddressAndSigner,
    algorand: AlgorandClient,
    dispenser: AddressAndSigner,
):
    """Test buying shares for Outcome A."""
    # Create a new account to act as the buyer
    buyer = algorand.account.random()

    # Fund the buyer account with ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=buyer.address, amount=10_000_000)
    )

    # Fetch the current state of shares_b from the contract
    shares_b = opinion_market_client.app_client.get_global_state().get("shares_b", 0)

    # Calculate the required payment amount manually
    price_a = shares_b + 1  # Replicate the contract's price_a logic
    quantity = 2  # Number of shares to buy
    required_amount = price_a * quantity  # Total payment amount

    # Create a payment transaction for buying shares
    payment_txn = algorand.transactions.payment(
        PayParams(
            sender=buyer.address,
            receiver=opinion_market_client.app_address,
            amount=required_amount*1_000_000,  # Use the manually calculated amount
            extra_fee=1_000,
        )
    )

    # Call the buy_shares_a method
    result = opinion_market_client.buy_shares_a(
        payment=TransactionWithSigner(txn=payment_txn, signer=buyer.signer),
        quantity=quantity,
        transaction_parameters=algokit_utils.TransactionParameters(
            sender=buyer.address,
            signer=buyer.signer,
        ),
    )

    assert result.confirmed_round

    assert opinion_market_client.app_client.get_global_state().get("shares_a", 0) == quantity

def test_buy_shares_b(
    opinion_market_client: OpinionTradingClient,
    creator: AddressAndSigner,
    algorand: AlgorandClient,
    dispenser: AddressAndSigner,
):
    """Test buying shares for Outcome B."""
    # Create a new account to act as the buyer
    buyer = algorand.account.random()

    # Fund the buyer account with ALGO
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=buyer.address, amount=10_000_000)
    )

    # Fetch the current state of shares_a from the contract
    shares_a = opinion_market_client.app_client.get_global_state().get("shares_a", 0)
    logger.info(f"shares_a: {shares_a}")

    # Calculate the required payment amount manually
    price_b = shares_a + 1  # Replicate the contract's price_b logic
    quantity = 2  # Number of shares to buy
    required_amount = price_b * quantity  # Total payment amount

    # Create a payment transaction for buying shares
    payment_txn = algorand.transactions.payment(
        PayParams(
            sender=buyer.address,
            receiver=opinion_market_client.app_address,
            amount=required_amount*1_000_000,  # Use the manually calculated amount
            extra_fee=1_000,
        )
    )

    # Call the buy_shares_b method
    result = opinion_market_client.buy_shares_b(
        payment=TransactionWithSigner(txn=payment_txn, signer=buyer.signer),
        quantity=quantity,
        transaction_parameters=algokit_utils.TransactionParameters(
            sender=buyer.address,
            signer=buyer.signer,
        ),
    )

    assert result.confirmed_round

    assert opinion_market_client.app_client.get_global_state().get("shares_b", 0) == quantity

def test_settle_market(
    opinion_market_client: OpinionTradingClient,
    creator: AddressAndSigner,
    algorand: AlgorandClient,
    dispenser: AddressAndSigner,
):
    """Test settling the market."""
    # Fetch the current state of shares_a and shares_b from the contract
    shares_a = opinion_market_client.app_client.get_global_state().get("shares_a", 0)
    shares_b = opinion_market_client.app_client.get_global_state().get("shares_b", 0)

    # Calculate the outcome based on the shares
    outcome = 1 if shares_a > shares_b else 2

    # Call the settle_market method
    result = opinion_market_client.settle_market(outcome=outcome)

    assert result.confirmed_round

    assert opinion_market_client.app_client.get_global_state().get("outcome", 0) == outcome
    assert opinion_market_client.app_client.get_global_state().get("shares_a", 0) == shares_a
    assert opinion_market_client.app_client.get_global_state().get("shares_b", 0) == shares_b

    # Try to settle the market again
    with pytest.raises(algosdk.error.AlgodHTTPError):
        opinion_market_client.settle_market(outcome=outcome)

def test_redeem_shares(
    opinion_market_client: OpinionTradingClient,
    creator: AddressAndSigner,
    algorand: AlgorandClient,
    dispenser: AddressAndSigner,
):
    """Test redeeming shares after the market is settled."""
    # Fetch the current state of shares_a and shares_b from the contract
    shares_a = opinion_market_client.app_client.get_global_state().get("shares_a", 0)
    shares_b = opinion_market_client.app_client.get_global_state().get("shares_b", 0)

    # Calculate the total shares
    total_shares = shares_a + shares_b

    # Calculate the redeem amount based on the shares and outcome
    outcome = opinion_market_client.app_client.get_global_state().get("outcome", 0)
    redeem_amount = (
        (dispenser.address.balance * shares_a) // total_shares
        if outcome == 1
        else (dispenser.address.balance * shares_b) // total_shares
    )

    # Call the redeem_shares method
    result = opinion_market_client.redeem_shares()

    assert result.confirmed_round

    assert dispenser.address.balance == redeem_amount

    # Try to redeem the shares again
    with pytest.raises(algosdk.error.AlgodHTTPError):
        opinion_market_client.redeem_shares()
