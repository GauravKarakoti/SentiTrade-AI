import type { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";

dotenv.config();

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.28",
    settings: {
      evmVersion: "cancun", // This explicitly enables the 'mcopy' opcode support
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    baseSepolia: {
      url: process.env.BASE_RPC_URL,
      accounts: process.env.EXECUTOR_PRIVATE_KEY ? [process.env.EXECUTOR_PRIVATE_KEY] : [],
    }
  },
};

export default config;