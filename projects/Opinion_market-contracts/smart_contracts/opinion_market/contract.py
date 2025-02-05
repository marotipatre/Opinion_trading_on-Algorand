from algopy import *
from algopy.arc4 import abimethod


class OpinionTrading(ARC4Contract):
    # State variables
    creator: Account
    market_question: String
    outcome_a: String
    outcome_b: String
    outcome: UInt64  # 0: Not settled, 1: Outcome A, 2: Outcome B
    shares_a: UInt64
    shares_b: UInt64
    expiration_time: UInt64  # Timestamp when the market expires
    # localState: LocalState[UInt64]  # Add this line

    def __init__(self) -> None:
        self.localState = LocalState(UInt64)

    # Create the opinion market
    @abimethod(allow_actions=["NoOp"], create="require")
    def create_market(
        self,
        market_question: String,
        outcome_a: String,
        outcome_b: String,
        expiration_time: UInt64,  # Expiration time in Unix timestamp
    ) -> None:
        assert (
            Global.latest_timestamp + expiration_time > Global.latest_timestamp
        ), "Expiration time must be in the future"
        self.creator = Txn.sender
        self.market_question = market_question
        self.outcome_a = outcome_a
        self.outcome_b = outcome_b
        self.outcome = UInt64(0)  # Market is not settled yet
        self.shares_a = UInt64(0)
        self.shares_b = UInt64(0)
        self.expiration_time = Global.latest_timestamp + expiration_time

    # Calculate dynamic price for Outcome A
    @subroutine()
    def price_a(self) -> UInt64:
        return self.shares_b + UInt64(
            1
        )  # Price increases with more shares of Outcome B

    # Calculate dynamic price for Outcome B
    @subroutine()
    def price_b(self) -> UInt64:
        return self.shares_a + UInt64(
            1
        )  # Price increases with more shares of Outcome A

    # Buy shares for Outcome A
    @abimethod()
    def buy_shares_a(self, payment: gtxn.PaymentTransaction) -> None:
        assert self.outcome == 0, "Market is already settled"
        assert Global.latest_timestamp < self.expiration_time, "Market has expired"
        assert payment.receiver == Global.current_application_address
        required_amount = self.price_a()
        assert payment.amount == 1_000_000, "Incorrect payment amount"
        val, exist = self.localState.maybe(Txn.sender)
        assert not exist, "Already ADDED OPINION"
        self.localState[Txn.sender] = UInt64(1)

        self.shares_a += 1

    # Buy shares for Outcome B
    @abimethod()
    def buy_shares_b(self, payment: gtxn.PaymentTransaction) -> None:
        assert self.outcome == 0, "Market is already settled"
        assert Global.latest_timestamp < self.expiration_time, "Market has expired"
        assert payment.receiver == Global.current_application_address
        assert payment.amount == 1_000_000, "Incorrect payment amount"
        val, exist = self.localState.maybe(Txn.sender)
        assert not exist, "Already ADDED OPINION"
        self.localState[Txn.sender] = UInt64(2)

        self.shares_b += 1

    # Settle the market (only the creator can settle)
    @abimethod()
    def settle_market(self) -> None:
        assert Txn.sender == self.creator, "Only the creator can settle the market"
        assert self.outcome == UInt64(0), "Market is already settled"
        assert (
            Global.latest_timestamp >= self.expiration_time
        ), "Market has not expired yet"

        if self.shares_a > self.shares_b:
            self.outcome = UInt64(1)
        else:
            self.outcome = UInt64(2)

    # Redeem shares after the market is settled
    @abimethod()
    def redeem_shares(self) -> None:
        assert self.outcome != 0, "Market is not settled yet"

        # Check if the user has bought shares
        user_choice, exist = self.localState.maybe(Txn.sender)
        assert exist, "User has not bought any shares"

        # Calculate the total shares for both outcomes
        total_shares = self.shares_a + self.shares_b

        # Calculate the total amount to be redistributed from wrong opinions
        if self.outcome == 1:  # Outcome A won
            wrong_shares = self.shares_b
        else:  # Outcome B won
            wrong_shares = self.shares_a

        # Total amount to be redistributed (50% of wrong opinions)
        total_redistribution = wrong_shares * 500_000  # 0.5 Algo per wrong share

        # Calculate the redeem amount based on the outcome
        if self.outcome == 1:  # Outcome A won
            if user_choice == 1:  # User bought shares for Outcome A (correct opinion)
                # User gets back 1 Algo + share of the redistribution
                redeem_amount = UInt64(1_000_000) + (
                    total_redistribution // self.shares_a
                )
            else:  # User bought shares for Outcome B (wrong opinion)
                # User gets back only 0.5 Algo
                redeem_amount = UInt64(500_000)
        else:  # Outcome B won
            if user_choice == 2:  # User bought shares for Outcome B (correct opinion)
                # User gets back 1 Algo + share of the redistribution
                redeem_amount = UInt64(1_000_000) + (
                    total_redistribution // self.shares_b
                )
            else:  # User bought shares for Outcome A (wrong opinion)
                # User gets back only 0.5 Algo
                redeem_amount = UInt64(500_000)

        # Deduct the fee from the user's redeem amount
        final_redeem_amount = redeem_amount - UInt64(1_000)

        # Transfer the redeemed amount to the sender
        itxn.Payment(
            receiver=Txn.sender,
            amount=final_redeem_amount,
            fee=1_000,
        ).submit()

        # Reset the user's local state to prevent double redemption
        del self.localState[Txn.sender]

    # Delete the application (only the creator can delete)
    @abimethod(allow_actions=["DeleteApplication"])
    def delete_application(self) -> None:
        assert Txn.sender == self.creator, "Only the creator can delete the application"

        # Transfer remaining funds to the creator
        itxn.Payment(
            receiver=self.creator,
            amount=0,
            close_remainder_to=self.creator,
            fee=1_000,
        ).submit()

    @abimethod(allow_actions=["OptIn"])
    def opt_in(self) -> None:
        pass
