/*
 * Storybook 8.6 · CRA5/Craco compatible.
 * Framework: react-webpack5 with @storybook/preset-create-react-app so CRA config (Craco)
 * powers the story build. React 19 supported natively in Storybook 8.6+.
 * Docs pinned to inline mode; docgen-typescript disabled (repo is JSX-only).
 */
module.exports = {
  stories: [
    '../src/os/**/*.stories.@(js|jsx)',
  ],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-a11y',
    '@storybook/addon-interactions',
    '@storybook/preset-create-react-app',
  ],
  framework: {
    name: '@storybook/react-webpack5',
    options: {},
  },
  core: {
    disableTelemetry: true,
    disableWhatsNewNotifications: true,
  },
  docs: {
    autodocs: false,
  },
  staticDirs: ['../public'],
  typescript: {
    reactDocgen: false,
  },
};
