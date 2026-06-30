// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

// 1. Mock SSI Index Token (Using standard 18 decimals)
contract MockIndexToken is ERC20 {
    address public router;
    
    constructor(string memory name, string memory symbol, address _router) ERC20(name, symbol) {
        router = _router;
    }
    
    function mint(address to, uint256 amount) external {
        require(msg.sender == router, "Only router can mint");
        _mint(to, amount);
    }
    
    function burn(address from, uint256 amount) external {
        require(msg.sender == router, "Only router can burn");
        _burn(from, amount);
    }
}

// 2. Mock SSI Protocol Router
contract MockSSIRouter {
    IERC20 public usdc;

    // As per SoSoValue Whitepaper 5.4: Base Value = 10
    // 10 USDC (6 decimals) = 10,000,000 units
    // 1 SSI Token (18 decimals) = 1,000,000,000,000,000,000 units

    constructor(address _usdc) {
        usdc = IERC20(_usdc);
    }

    function mint(address indexToken, uint256 usdcAmount) external returns (uint256) {
        require(usdc.transferFrom(msg.sender, address(this), usdcAmount), "USDC transfer failed");
        
        // Calculate Index Shares to mint (10 USDC = 1 SSI)
        // Formula: (usdcAmount * 10^18) / (10 * 10^6) = usdcAmount * 10^11
        uint256 shares = usdcAmount * 10**11;
        
        MockIndexToken(indexToken).mint(msg.sender, shares);
        return shares;
    }

    function redeem(address indexToken, uint256 shares) external returns (uint256) {
        MockIndexToken(indexToken).burn(msg.sender, shares);
        
        // Calculate USDC to return
        // Formula: shares / 10^11
        uint256 usdcAmount = shares / 10**11;
        
        require(usdc.transfer(msg.sender, usdcAmount), "USDC return failed");
        return usdcAmount;
    }
}